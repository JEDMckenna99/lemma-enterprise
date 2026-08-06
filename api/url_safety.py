"""
URL safety helpers: SSRF-safe outbound URL validation and open-redirect guards.

Two distinct concerns:

1. Outbound fetches (server makes an HTTP request to a URL the client influenced)
   must not be pointed at internal/link-local/loopback/metadata addresses.
   ``is_safe_outbound_url`` enforces an http(s) scheme and validates every DNS
   answer against a public-address policy.

2. Redirects (server sends the browser to a URL the client influenced) must not
   become open redirects. ``is_safe_relative_redirect`` accepts only same-origin
   relative paths (rejecting protocol-relative ``//host`` and ``/\\host`` tricks);
   ``is_host_allowed_redirect`` accepts absolute https URLs whose host is in an
   explicit allowlist (exact host or subdomain).
"""

from __future__ import annotations

import http.client
import ipaddress
import logging
import socket
import ssl
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_ALLOWED_OUTBOUND_SCHEMES = {"http", "https"}
_DEFAULT_FETCH_MAX_BYTES = 64 * 1024


def _ip_is_public(ip: ipaddress._BaseAddress) -> bool:
    """True only for globally-routable public addresses."""
    # Unwrap IPv4-mapped/compat IPv6 so ``::ffff:169.254.169.254`` is caught.
    if isinstance(ip, ipaddress.IPv6Address):
        mapped = ip.ipv4_mapped
        if mapped is not None:
            return _ip_is_public(mapped)

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return False

    # ``is_global`` additionally excludes ranges like 100.64.0.0/10 (CGNAT).
    try:
        if not ip.is_global:
            return False
    except AttributeError:  # pragma: no cover - very old stdlib
        pass

    return True


@dataclass(frozen=True)
class SafeOutboundTarget:
    """DNS-validated outbound target with a pinned public IP for the request."""

    url: str
    scheme: str
    hostname: str
    port: int
    path: str
    pinned_ip: str


def resolve_safe_outbound_target(url: Optional[str]) -> Tuple[Optional[SafeOutboundTarget], str]:
    """
    Resolve ``url`` once and return a target pinned to a public IP.

    Fails closed if the scheme is not http(s), the host cannot be resolved, or
    *any* DNS answer is non-public. Callers should connect to ``pinned_ip`` while
    keeping TLS SNI / Host equal to ``hostname`` so DNS rebinding between check
    and connect cannot retarget the request.
    """
    if not url or not isinstance(url, str):
        return None, "empty_url"

    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_OUTBOUND_SCHEMES:
        return None, "scheme_not_allowed"

    host = parsed.hostname
    if not host:
        return None, "missing_host"

    default_port = 443 if scheme == "https" else 80
    try:
        port = parsed.port or default_port
    except ValueError:
        return None, "invalid_port"

    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except Exception:
        return None, "dns_resolution_failed"

    if not infos:
        return None, "dns_no_records"

    public_ips: list[str] = []
    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        # Strip IPv6 scope id if present (e.g. "fe80::1%eth0").
        ip_str = ip_str.split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return None, "invalid_ip"
        if not _ip_is_public(ip):
            return None, "private_or_reserved_ip"
        if ip_str not in public_ips:
            public_ips.append(ip_str)

    if not public_ips:
        return None, "dns_no_records"

    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    return (
        SafeOutboundTarget(
            url=url.strip(),
            scheme=scheme,
            hostname=host,
            port=int(port),
            path=path,
            pinned_ip=public_ips[0],
        ),
        "ok",
    )


def is_safe_outbound_url(url: Optional[str]) -> Tuple[bool, str]:
    """
    Validate a URL is safe for the server to fetch (SSRF guard).

    Returns ``(ok, reason)``. ``ok`` is True only when the scheme is http/https,
    the host resolves, and *every* resolved address is a public IP. This blocks
    loopback (127.0.0.0/8, ::1), private (RFC1918, fc00::/7), link-local
    (169.254.0.0/16 incl. the cloud metadata endpoint, fe80::/10), and other
    reserved/multicast/unspecified ranges.

    Prefer ``fetch_safe_outbound_text`` (or ``resolve_safe_outbound_target`` plus
    a pinned connect) for actual fetches so DNS rebinding cannot retarget the
    connection after this check.
    """
    target, reason = resolve_safe_outbound_target(url)
    return target is not None, reason


def fetch_safe_outbound_text(
    url: Optional[str],
    *,
    timeout: float = 10.0,
    max_bytes: int = _DEFAULT_FETCH_MAX_BYTES,
    method: str = "GET",
) -> Tuple[bool, str, Optional[str]]:
    """
    Fetch ``url`` with DNS validated once and the TCP connect pinned to that IP.

    TLS uses SNI + certificate verification for the original hostname. Redirects
    are not followed. Response bodies larger than ``max_bytes`` fail closed.
    Returns ``(ok, reason, body_text)``.
    """
    target, reason = resolve_safe_outbound_target(url)
    if target is None:
        return False, reason, None

    conn: Optional[http.client.HTTPConnection] = None
    try:
        sock = socket.create_connection((target.pinned_ip, target.port), timeout=timeout)
        if target.scheme == "https":
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=target.hostname)
            conn = http.client.HTTPSConnection(target.hostname, target.port, timeout=timeout)
        else:
            conn = http.client.HTTPConnection(target.hostname, target.port, timeout=timeout)
        # Pin the already-validated socket so a later DNS answer cannot retarget us.
        conn.sock = sock
        conn.request(
            method.upper(),
            target.path,
            headers={
                "Host": target.hostname,
                "Accept": "text/plain,*/*",
                "Connection": "close",
                "User-Agent": "lemma-url-safety/1.0",
            },
        )
        response = conn.getresponse()
        # Redirects are never followed — callers must not chase Location.
        if response.status in {301, 302, 303, 307, 308}:
            return False, "redirect_not_allowed", None
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            return False, "response_too_large", None
        if response.status != 200:
            return False, f"http_{response.status}", None
        return True, "ok", raw.decode("utf-8", errors="replace")
    except ssl.SSLError as exc:
        logger.warning("Pinned outbound TLS failed for %s: %s", target.hostname, exc)
        return False, "tls_failed", None
    except Exception as exc:
        logger.warning("Pinned outbound fetch failed for %s: %s", target.hostname, exc)
        return False, "fetch_failed", None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def is_safe_relative_redirect(target: Optional[str]) -> bool:
    """
    True only for a same-origin relative path.

    Accepts ``/dashboard`` but rejects absolute URLs, protocol-relative
    ``//evil.com``, backslash variants ``/\\evil.com`` (which some browsers
    normalize to ``//``), and anything containing control/whitespace that could
    be used to smuggle a second target.
    """
    if not target or not isinstance(target, str):
        return False
    text = target.strip()
    if not text.startswith("/"):
        return False
    if text.startswith("//") or text.startswith("/\\") or text.startswith("/%2f") or text.startswith("/%5c"):
        return False
    if any(ch in text for ch in ("\\", "\n", "\r", "\t", "\x00")):
        return False
    return True


def _normalize_host(value: Optional[str]) -> str:
    return (value or "").strip().lower().rstrip(".")


def is_host_allowed_redirect(target: Optional[str], allowed_hosts: Iterable[str]) -> bool:
    """
    True for an absolute https URL whose host is in ``allowed_hosts``.

    A host matches when it equals an allowed host or is a subdomain of it
    (``app.example.com`` matches allowed ``example.com``). Requires https so an
    attacker cannot downgrade to a lookalike scheme.
    """
    if not target or not isinstance(target, str):
        return False

    parsed = urlparse(target.strip())
    if (parsed.scheme or "").lower() != "https":
        return False

    host = _normalize_host(parsed.hostname)
    if not host:
        return False

    for allowed in allowed_hosts or ():
        a = _normalize_host(allowed)
        if a and (host == a or host.endswith("." + a)):
            return True
    return False

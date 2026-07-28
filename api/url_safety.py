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

import ipaddress
import socket
from typing import Iterable, Optional, Tuple
from urllib.parse import urlparse

_ALLOWED_OUTBOUND_SCHEMES = {"http", "https"}


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


def is_safe_outbound_url(url: Optional[str]) -> Tuple[bool, str]:
    """
    Validate a URL is safe for the server to fetch (SSRF guard).

    Returns ``(ok, reason)``. ``ok`` is True only when the scheme is http/https,
    the host resolves, and *every* resolved address is a public IP. This blocks
    loopback (127.0.0.0/8, ::1), private (RFC1918, fc00::/7), link-local
    (169.254.0.0/16 incl. the cloud metadata endpoint, fe80::/10), and other
    reserved/multicast/unspecified ranges.

    Note: this validates at resolution time. It is a strong first-line defense
    but does not by itself defeat DNS-rebinding TOCTOU; callers that need that
    should additionally pin the connection to the validated address.
    """
    if not url or not isinstance(url, str):
        return False, "empty_url"

    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_OUTBOUND_SCHEMES:
        return False, "scheme_not_allowed"

    host = parsed.hostname
    if not host:
        return False, "missing_host"

    default_port = 443 if scheme == "https" else 80
    try:
        port = parsed.port or default_port
    except ValueError:
        return False, "invalid_port"

    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except Exception:
        return False, "dns_resolution_failed"

    if not infos:
        return False, "dns_no_records"

    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        # Strip IPv6 scope id if present (e.g. "fe80::1%eth0").
        ip_str = ip_str.split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False, "invalid_ip"
        if not _ip_is_public(ip):
            return False, "private_or_reserved_ip"

    return True, "ok"


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

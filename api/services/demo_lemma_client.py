"""
Real control-plane client for the public demo surface.

This module only calls production Lemma APIs and returns upstream results
without inventing authorization outcomes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


class DemoClientError(RuntimeError):
    """Raised when an upstream control-plane call fails."""


@dataclass
class DemoLemmaClient:
    base_url: str
    service_agent_token: str
    timeout_seconds: float = 15.0

    def __post_init__(self) -> None:
        self.base_url = str(self.base_url or "").rstrip("/")
        if not self.base_url:
            raise DemoClientError("LEMMA_DEMO_BASE_URL is required")
        if not self.service_agent_token:
            raise DemoClientError("LEMMA_DEMO_SERVICE_AGENT_TOKEN is required")
        self._http = requests.Session()

    @classmethod
    def from_env(cls) -> "DemoLemmaClient":
        return cls(
            base_url=os.getenv("LEMMA_DEMO_BASE_URL", "https://lemma.id"),
            service_agent_token=str(os.getenv("LEMMA_DEMO_SERVICE_AGENT_TOKEN", "")).strip(),
            timeout_seconds=float(os.getenv("LEMMA_DEMO_TIMEOUT_SECONDS", "15") or "15"),
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        expected_statuses: set[int] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        request_headers = {"Content-Type": "application/json", "X-Agent-Token": self.service_agent_token}
        if headers:
            request_headers.update(headers)
        response = self._http.request(
            method.upper(),
            url,
            json=json_payload,
            headers=request_headers,
            timeout=self.timeout_seconds,
        )
        if expected_statuses is None:
            expected_statuses = {200}
        body: dict[str, Any]
        try:
            body = response.json() if response.content else {}
            if not isinstance(body, dict):
                body = {"raw": body}
        except Exception:
            body = {"raw": response.text}
        body["_status"] = response.status_code
        if response.status_code not in expected_statuses:
            raise DemoClientError(f"upstream_error:{path}:{response.status_code}:{body}")
        return body

    def issue_proof(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/agent/credentials/issue",
            json_payload=payload,
            expected_statuses={200},
        )

    def validate_token(self, token: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/agent/validate",
            headers={"X-Agent-Token": token},
            expected_statuses={200, 401},
        )

    def revoke_proof(self, token_id: str, reason: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/agent/credentials/{token_id}/revoke",
            json_payload={"reason": reason},
            expected_statuses={200, 404},
        )

    def revocation_status(self, token_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/api/wallet/revocation-status?credential_ids={token_id}",
            expected_statuses={200, 404},
        )

    def revocation_delta(self, since: int) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/api/authz/revocation/delta?since={int(since)}&limit=200",
            expected_statuses={200},
            headers={"X-Agent-Token": self.service_agent_token},
        )

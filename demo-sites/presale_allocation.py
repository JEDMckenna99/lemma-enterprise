"""Site-local presale code ledger — one allocation per (drop_id, verified person).

Copy-paste reference for relying sites. Lemma.id does not host drop counters;
the integrator keys allocations off the verified site-private PPID.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AllocationRecord:
    drop_id: str
    ppid: str
    code: str
    claimed_at: float
    assurance: Optional[str] = None


@dataclass(frozen=True)
class ClaimResult:
    ok: bool
    reason: str
    code: Optional[str] = None
    ppid: Optional[str] = None
    drop_id: Optional[str] = None
    claimed_at: Optional[float] = None
    assurance: Optional[str] = None
    existing: Optional[AllocationRecord] = None


def _normalize_drop_id(drop_id: str) -> str:
    return str(drop_id or "").strip()


def _normalize_ppid(ppid: str) -> str:
    return str(ppid or "").strip()


def _generate_code() -> str:
    return f"{random.randint(10_000_000, 99_999_999)}"


class PresaleAllocationLedger:
    """Thread-safe in-memory ledger: at most one code per (drop_id, ppid)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_key: dict[tuple[str, str], AllocationRecord] = {}

    def _subject_keys(self, drop_id: str, ppid: str, *, legacy_ppid: Optional[str] = None) -> list[tuple[str, str]]:
        drop = _normalize_drop_id(drop_id)
        keys: list[tuple[str, str]] = []
        for candidate in (ppid, legacy_ppid):
            normalized = _normalize_ppid(candidate or "")
            if normalized:
                keys.append((drop, normalized))
        return keys

    def lookup(
        self,
        drop_id: str,
        ppid: str,
        *,
        legacy_ppid: Optional[str] = None,
    ) -> Optional[AllocationRecord]:
        drop = _normalize_drop_id(drop_id)
        if not drop:
            return None
        with self._lock:
            for key in self._subject_keys(drop, ppid, legacy_ppid=legacy_ppid):
                record = self._by_key.get(key)
                if record:
                    return record
        return None

    def claim(
        self,
        drop_id: str,
        ppid: str,
        *,
        legacy_ppid: Optional[str] = None,
        assurance: Optional[str] = None,
    ) -> ClaimResult:
        drop = _normalize_drop_id(drop_id)
        canonical = _normalize_ppid(ppid)
        if not drop:
            return ClaimResult(False, "drop_id_missing")
        if not canonical:
            return ClaimResult(False, "ppid_missing")

        with self._lock:
            for key in self._subject_keys(drop, canonical, legacy_ppid=legacy_ppid):
                existing = self._by_key.get(key)
                if existing:
                    return ClaimResult(
                        False,
                        "allocation_already_claimed",
                        ppid=canonical,
                        drop_id=drop,
                        existing=existing,
                    )

            code = _generate_code()
            while any(record.code == code for record in self._by_key.values()):
                code = _generate_code()

            claimed_at = time.time()
            record = AllocationRecord(
                drop_id=drop,
                ppid=canonical,
                code=code,
                claimed_at=claimed_at,
                assurance=assurance,
            )
            self._by_key[(drop, canonical)] = record
            if legacy_ppid:
                legacy = _normalize_ppid(legacy_ppid)
                if legacy and legacy != canonical:
                    self._by_key[(drop, legacy)] = record

            return ClaimResult(
                True,
                "ok",
                code=code,
                ppid=canonical,
                drop_id=drop,
                claimed_at=claimed_at,
                assurance=assurance,
            )

    def reset(self, drop_id: Optional[str] = None) -> int:
        """Demo-only: clear allocations. Returns number of records removed."""
        with self._lock:
            if drop_id is None:
                count = len(self._by_key)
                self._by_key.clear()
                return count
            drop = _normalize_drop_id(drop_id)
            keys = [key for key in self._by_key if key[0] == drop]
            for key in keys:
                del self._by_key[key]
            return len(keys)

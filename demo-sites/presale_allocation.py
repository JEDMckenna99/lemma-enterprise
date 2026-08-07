"""Site-local presale code ledger, one allocation per (drop_id, verified person).

Copy-paste reference for relying sites. Lemma.id does not host drop counters;
the integrator keys allocations off the verified site-private PPID.
"""

from __future__ import annotations

import os
import random
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Optional, Protocol


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


@dataclass(frozen=True)
class RegisterResult:
    ok: bool
    reason: str
    drop_id: Optional[str] = None
    ppid: Optional[str] = None


def _normalize_drop_id(drop_id: str) -> str:
    return str(drop_id or "").strip()


def _normalize_ppid(ppid: str) -> str:
    return str(ppid or "").strip()


def _generate_code() -> str:
    return f"{random.randint(10_000_000, 99_999_999)}"


class PresaleRegistrationBackend(Protocol):
    def register(
        self,
        drop_id: str,
        ppid: str,
        *,
        email: str = "",
        phone: str = "",
    ) -> RegisterResult:
        ...

    def is_registered(
        self,
        drop_id: str,
        ppid: str,
        *,
        legacy_ppid: Optional[str] = None,
    ) -> bool:
        ...

    def reset(self, drop_id: Optional[str] = None) -> int:
        ...


class PresaleAllocationBackend(Protocol):
    def lookup(
        self,
        drop_id: str,
        ppid: str,
        *,
        legacy_ppid: Optional[str] = None,
    ) -> Optional[AllocationRecord]:
        ...

    def claim(
        self,
        drop_id: str,
        ppid: str,
        *,
        legacy_ppid: Optional[str] = None,
        assurance: Optional[str] = None,
    ) -> ClaimResult:
        ...

    def clear_claim(
        self,
        drop_id: str,
        ppid: str,
        *,
        legacy_ppid: Optional[str] = None,
    ) -> int:
        ...

    def reset(self, drop_id: Optional[str] = None) -> int:
        ...


class PresaleRegistrationStore:
    """Site-local presale signups keyed by (drop_id, ppid), Laylo registration step."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._registered: dict[tuple[str, str], dict] = {}

    def register(
        self,
        drop_id: str,
        ppid: str,
        *,
        email: str = "",
        phone: str = "",
    ) -> RegisterResult:
        drop = _normalize_drop_id(drop_id)
        subject = _normalize_ppid(ppid)
        if not drop:
            return RegisterResult(False, "drop_id_missing")
        if not subject:
            return RegisterResult(False, "ppid_missing")
        with self._lock:
            self._registered[(drop, subject)] = {
                "email": str(email or "").strip(),
                "phone": str(phone or "").strip(),
                "registered_at": time.time(),
            }
        return RegisterResult(True, "ok", drop_id=drop, ppid=subject)

    def update_contact(
        self,
        drop_id: str,
        ppid: str,
        *,
        email: str = "",
        phone: str = "",
    ) -> RegisterResult:
        drop = _normalize_drop_id(drop_id)
        subject = _normalize_ppid(ppid)
        if not drop:
            return RegisterResult(False, "drop_id_missing")
        if not subject:
            return RegisterResult(False, "ppid_missing")
        with self._lock:
            key = (drop, subject)
            if key not in self._registered:
                return RegisterResult(False, "registration_required")
            self._registered[key]["email"] = str(email or "").strip()
            self._registered[key]["phone"] = str(phone or "").strip()
        return RegisterResult(True, "ok", drop_id=drop, ppid=subject)

    def is_registered(
        self,
        drop_id: str,
        ppid: str,
        *,
        legacy_ppid: Optional[str] = None,
    ) -> bool:
        drop = _normalize_drop_id(drop_id)
        if not drop:
            return False
        with self._lock:
            for candidate in (ppid, legacy_ppid):
                normalized = _normalize_ppid(candidate or "")
                if normalized and (drop, normalized) in self._registered:
                    return True
        return False

    def reset(self, drop_id: Optional[str] = None) -> int:
        with self._lock:
            if drop_id is None:
                count = len(self._registered)
                self._registered.clear()
                return count
            drop = _normalize_drop_id(drop_id)
            keys = [key for key in self._registered if key[0] == drop]
            for key in keys:
                del self._registered[key]
            return len(keys)


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

    def clear_claim(
        self,
        drop_id: str,
        ppid: str,
        *,
        legacy_ppid: Optional[str] = None,
    ) -> int:
        """Demo helper: release this person's allocation so they can claim again."""
        drop = _normalize_drop_id(drop_id)
        if not drop:
            return 0
        with self._lock:
            codes: set[str] = set()
            for key in self._subject_keys(drop, ppid, legacy_ppid=legacy_ppid):
                record = self._by_key.get(key)
                if record:
                    codes.add(record.code)
            if not codes:
                return 0
            keys = [
                key
                for key, record in self._by_key.items()
                if key[0] == drop and record.code in codes
            ]
            for key in keys:
                del self._by_key[key]
            return len(keys)

    def reset(self, drop_id: Optional[str] = None) -> int:
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


class SQLitePresaleStore(PresaleRegistrationStore, PresaleAllocationLedger):
    """Transactional SQLite reference adapter for demo/staging deployments."""

    def __init__(self, db_path: str) -> None:
        self._db_path = str(db_path or ":memory:")
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS presale_registrations (
                    drop_id TEXT NOT NULL,
                    ppid TEXT NOT NULL,
                    email TEXT,
                    phone TEXT,
                    registered_at REAL NOT NULL,
                    PRIMARY KEY (drop_id, ppid)
                );
                CREATE TABLE IF NOT EXISTS presale_allocations (
                    drop_id TEXT NOT NULL,
                    ppid TEXT NOT NULL,
                    code TEXT NOT NULL UNIQUE,
                    claimed_at REAL NOT NULL,
                    assurance TEXT,
                    PRIMARY KEY (drop_id, ppid)
                );
                """
            )
            self._conn.commit()

    def register(
        self,
        drop_id: str,
        ppid: str,
        *,
        email: str = "",
        phone: str = "",
    ) -> RegisterResult:
        drop = _normalize_drop_id(drop_id)
        subject = _normalize_ppid(ppid)
        if not drop:
            return RegisterResult(False, "drop_id_missing")
        if not subject:
            return RegisterResult(False, "ppid_missing")
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO presale_registrations (drop_id, ppid, email, phone, registered_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(drop_id, ppid) DO UPDATE SET
                        email=excluded.email,
                        phone=excluded.phone,
                        registered_at=excluded.registered_at
                    """,
                    (drop, subject, str(email or "").strip(), str(phone or "").strip(), time.time()),
                )
                self._conn.commit()
            except sqlite3.Error:
                self._conn.rollback()
                return RegisterResult(False, "registration_store_error")
        return RegisterResult(True, "ok", drop_id=drop, ppid=subject)

    def update_contact(
        self,
        drop_id: str,
        ppid: str,
        *,
        email: str = "",
        phone: str = "",
    ) -> RegisterResult:
        drop = _normalize_drop_id(drop_id)
        subject = _normalize_ppid(ppid)
        if not drop:
            return RegisterResult(False, "drop_id_missing")
        if not subject:
            return RegisterResult(False, "ppid_missing")
        with self._lock:
            try:
                cur = self._conn.execute(
                    """
                    UPDATE presale_registrations
                    SET email = ?, phone = ?
                    WHERE drop_id = ? AND ppid = ?
                    """,
                    (str(email or "").strip(), str(phone or "").strip(), drop, subject),
                )
                self._conn.commit()
                if cur.rowcount < 1:
                    return RegisterResult(False, "registration_required")
            except sqlite3.Error:
                self._conn.rollback()
                return RegisterResult(False, "registration_store_error")
        return RegisterResult(True, "ok", drop_id=drop, ppid=subject)

    def is_registered(
        self,
        drop_id: str,
        ppid: str,
        *,
        legacy_ppid: Optional[str] = None,
    ) -> bool:
        drop = _normalize_drop_id(drop_id)
        if not drop:
            return False
        with self._lock:
            for candidate in (ppid, legacy_ppid):
                normalized = _normalize_ppid(candidate or "")
                if not normalized:
                    continue
                row = self._conn.execute(
                    "SELECT 1 FROM presale_registrations WHERE drop_id = ? AND ppid = ? LIMIT 1",
                    (drop, normalized),
                ).fetchone()
                if row:
                    return True
        return False

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
            for candidate in (ppid, legacy_ppid):
                normalized = _normalize_ppid(candidate or "")
                if not normalized:
                    continue
                row = self._conn.execute(
                    """
                    SELECT drop_id, ppid, code, claimed_at, assurance
                    FROM presale_allocations
                    WHERE drop_id = ? AND ppid = ?
                    LIMIT 1
                    """,
                    (drop, normalized),
                ).fetchone()
                if row:
                    return AllocationRecord(
                        drop_id=row[0],
                        ppid=row[1],
                        code=row[2],
                        claimed_at=float(row[3]),
                        assurance=row[4],
                    )
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
            for candidate in (canonical, legacy_ppid):
                normalized = _normalize_ppid(candidate or "")
                if not normalized:
                    continue
                existing = self.lookup(drop, normalized)
                if existing:
                    return ClaimResult(
                        False,
                        "allocation_already_claimed",
                        ppid=canonical,
                        drop_id=drop,
                        existing=existing,
                    )

            code = _generate_code()
            claimed_at = time.time()
            try:
                self._conn.execute(
                    """
                    INSERT INTO presale_allocations (drop_id, ppid, code, claimed_at, assurance)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (drop, canonical, code, claimed_at, assurance),
                )
                if legacy_ppid:
                    legacy = _normalize_ppid(legacy_ppid)
                    if legacy and legacy != canonical:
                        self._conn.execute(
                            """
                            INSERT OR IGNORE INTO presale_allocations (drop_id, ppid, code, claimed_at, assurance)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (drop, legacy, code, claimed_at, assurance),
                        )
                self._conn.commit()
            except sqlite3.IntegrityError:
                self._conn.rollback()
                existing = self.lookup(drop, canonical, legacy_ppid=legacy_ppid)
                if existing:
                    return ClaimResult(
                        False,
                        "allocation_already_claimed",
                        ppid=canonical,
                        drop_id=drop,
                        existing=existing,
                    )
                return ClaimResult(False, "allocation_store_error")
            except sqlite3.Error:
                self._conn.rollback()
                return ClaimResult(False, "allocation_store_error")

            record = AllocationRecord(
                drop_id=drop,
                ppid=canonical,
                code=code,
                claimed_at=claimed_at,
                assurance=assurance,
            )
            return ClaimResult(
                True,
                "ok",
                code=code,
                ppid=canonical,
                drop_id=drop,
                claimed_at=claimed_at,
                assurance=assurance,
                existing=record,
            )

    def clear_claim(
        self,
        drop_id: str,
        ppid: str,
        *,
        legacy_ppid: Optional[str] = None,
    ) -> int:
        """Demo helper: release this person's allocation so they can claim again."""
        drop = _normalize_drop_id(drop_id)
        if not drop:
            return 0
        subjects: list[str] = []
        for candidate in (ppid, legacy_ppid):
            normalized = _normalize_ppid(candidate or "")
            if normalized and normalized not in subjects:
                subjects.append(normalized)
        if not subjects:
            return 0
        with self._lock:
            codes: set[str] = set()
            for subject in subjects:
                row = self._conn.execute(
                    "SELECT code FROM presale_allocations WHERE drop_id = ? AND ppid = ?",
                    (drop, subject),
                ).fetchone()
                if row:
                    codes.add(row[0])
            if not codes:
                return 0
            removed = 0
            try:
                for code in codes:
                    cur = self._conn.execute(
                        "DELETE FROM presale_allocations WHERE drop_id = ? AND code = ?",
                        (drop, code),
                    )
                    removed += int(cur.rowcount or 0)
                self._conn.commit()
            except sqlite3.Error:
                self._conn.rollback()
                return 0
            return removed

    def reset(self, drop_id: Optional[str] = None) -> int:
        with self._lock:
            if drop_id is None:
                reg = self._conn.execute("DELETE FROM presale_registrations").rowcount
                alloc = self._conn.execute("DELETE FROM presale_allocations").rowcount
                self._conn.commit()
                return int(reg or 0) + int(alloc or 0)
            drop = _normalize_drop_id(drop_id)
            reg = self._conn.execute(
                "DELETE FROM presale_registrations WHERE drop_id = ?",
                (drop,),
            ).rowcount
            alloc = self._conn.execute(
                "DELETE FROM presale_allocations WHERE drop_id = ?",
                (drop,),
            ).rowcount
            self._conn.commit()
            return int(reg or 0) + int(alloc or 0)


def create_presale_stores() -> tuple[PresaleRegistrationBackend, PresaleAllocationBackend]:
    """Factory: in-memory by default, SQLite when LEMMA_PRESALE_SQLITE_PATH is set."""
    db_path = os.getenv("LEMMA_PRESALE_SQLITE_PATH", "").strip()
    if db_path:
        store = SQLitePresaleStore(db_path)
        return store, store
    return PresaleRegistrationStore(), PresaleAllocationLedger()

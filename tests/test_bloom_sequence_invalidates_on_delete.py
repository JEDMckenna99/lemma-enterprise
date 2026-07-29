"""Bloom sequence must change when revocation rows are deleted (Unban)."""

from __future__ import annotations


def test_fetch_revocation_sequence_number_changes_when_row_count_drops(monkeypatch):
    from api import bloom_snapshot
    import api.database as database_mod

    class _Cursor:
        def __init__(self, row):
            self._row = row

        def execute(self, *_args, **_kwargs):
            return None

        def fetchone(self):
            return self._row

        def close(self):
            return None

    class _Conn:
        def __init__(self, row):
            self._row = row

        def cursor(self):
            return _Cursor(self._row)

        def close(self):
            return None

    # Same MAX(id)=99, but COUNT drops after Unban deletes a row.
    monkeypatch.setattr(database_mod, "get_db_connection", lambda: _Conn((99, 5, 250)))
    before = bloom_snapshot.fetch_revocation_sequence_number()

    monkeypatch.setattr(database_mod, "get_db_connection", lambda: _Conn((99, 4, 200)))
    after = bloom_snapshot.fetch_revocation_sequence_number()

    assert before != after
    assert before > 0
    assert after > 0

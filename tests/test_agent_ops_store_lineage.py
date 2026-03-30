import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.agent_ops_store import _delegation_lineage_from_row  # pylint: disable=protected-access


def test_delegation_lineage_from_row_maps_expected_fields():
    now = datetime.now(timezone.utc)
    row = (
        "dlg_1",
        "agt_1",
        "lemma-firewall-default",
        "did:lemma:ppid_" + ("a" * 64),
        "owner@example.com",
        "did:lemma:ppid_" + ("b" * 64),
        "actor@example.com",
        "did:lemma:ppid_" + ("c" * 64),
        "requester@example.com",
        "agent_credential",
        "agt_1",
        "lemma.id",
        ["read", "write"],
        ["lemma.id"],
        {"fs.write": ["C:/workspace/**"]},
        ["C:/workspace/docs/**"],
        10,
        now,
        None,
        "active",
        "delegated_for_task",
        "hash_123",
    )
    lineage = _delegation_lineage_from_row(row)
    assert lineage is not None
    assert lineage["delegation_id"] == "dlg_1"
    assert lineage["scope"] == ["read", "write"]
    assert lineage["resource_bounds"]["fs.write"] == ["C:/workspace/**"]
    assert lineage["max_operations"] == 10
    assert lineage["status"] == "active"

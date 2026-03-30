import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import agent_ops_store


def test_runtime_row_to_dict_includes_trust_and_control_fields():
    row = (
        "runtime_demo",
        "main",
        "workspace_demo",
        "org_default",
        "prod",
        "passkey_root",
        "lemma.id",
        "OpenClaw Runtime",
        "runtime_default_v1",
        "v7",
        {"critical": "proof_required"},
        "tainted_external",
        4,
        True,
        True,
        {"ops_per_hour": 50},
        False,
        None,
        None,
        None,
        None,
        "Killed for test",
    )

    # pylint: disable=protected-access
    payload = agent_ops_store._runtime_row_to_dict(row)

    assert payload["runtime_id"] == "runtime_demo"
    assert payload["policy_profile"] == "runtime_default_v1"
    assert payload["policy_profile_version"] == "v7"
    assert payload["trust_state"] == "tainted_external"
    assert payload["taint_epoch"] == 4
    assert payload["kill_switch_enabled"] is True
    assert payload["emergency_stopped"] is True
    assert payload["quota_json"] == {"ops_per_hour": 50}
    assert payload["active"] is False
    assert payload["kill_reason"] == "Killed for test"

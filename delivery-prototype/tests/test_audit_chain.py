from config import DEVICE_KEY_PATH
from crypto.device_keys import ensure_device_keypair
from crypto.verifier import sign_delivery_event
from models.schemas import new_event_id


def test_audit_chain_happy_path(client, seeded_route):
    device = ensure_device_keypair(DEVICE_KEY_PATH)
    credential = seeded_route["credential"]
    pkg = seeded_route["packages"][0]
    event = sign_delivery_event(
        {
            "event_id": new_event_id(),
            "event_type": "DELIVERED",
            "package_id": pkg["package_id"],
            "route_id": credential["route_id"],
            "stop_id": pkg["stop_id"],
            "timestamp": "2026-06-16T18:42:11Z",
            "gps_precision_bucket": "within_50m",
            "proof": {"photo_hash": "fake", "requirements_met": True},
            "device_id": credential["device_id"],
        },
        device,
        credential,
        None,
    )
    route_id = seeded_route["route_id"]
    client.post("/api/sync/events", json={"route_id": route_id, "events": [event]})
    res = client.get(f"/api/audit/chain/{route_id}")
    data = res.get_json()
    assert data["tamper_free"] is True
    assert any(s["step"] == "no_tampering_detected" and s["valid"] for s in data["steps"])

from config import DEVICE_KEY_PATH
from crypto.device_keys import ensure_device_keypair
from crypto.verifier import sign_delivery_event
from models.schemas import new_event_id


def _signed_event(seeded_route, prior=None):
    device = ensure_device_keypair(DEVICE_KEY_PATH)
    credential = seeded_route["credential"]
    pkg = seeded_route["packages"][0]
    unsigned = {
        "event_id": new_event_id(),
        "event_type": "DELIVERED",
        "package_id": pkg["package_id"],
        "route_id": credential["route_id"],
        "stop_id": pkg["stop_id"],
        "timestamp": "2026-06-16T18:42:11Z",
        "gps_precision_bucket": "within_50m",
        "proof": {"photo_hash": "fake", "requirements_met": True},
        "device_id": credential["device_id"],
    }
    return sign_delivery_event(unsigned, device, credential, prior)


def test_sync_events(client, seeded_route):
    event = _signed_event(seeded_route)
    route_id = seeded_route["route_id"]
    res = client.post("/api/sync/events", json={"route_id": route_id, "events": [event]})
    assert res.status_code == 200
    data = res.get_json()
    assert data["results"][0]["status"] == "synced"

    dup = client.post("/api/sync/events", json={"route_id": route_id, "events": [event]})
    assert dup.get_json()["results"][0]["status"] == "synced"


def test_sync_status(client, seeded_route):
    event = _signed_event(seeded_route)
    route_id = seeded_route["route_id"]
    client.post("/api/sync/events", json={"route_id": route_id, "events": [event]})
    res = client.get(f"/api/sync/status/{route_id}")
    assert res.status_code == 200
    assert len(res.get_json()["events"]) >= 1

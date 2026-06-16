from config import DEVICE_KEY_PATH
from crypto.device_keys import ensure_device_keypair
from crypto.verifier import sign_delivery_event, verify_delivery_event
from models.schemas import new_event_id


def _make_event(seeded_route, package_id="P-1001", prior=None):
    device = ensure_device_keypair(DEVICE_KEY_PATH)
    credential = seeded_route["credential"]
    unsigned = {
        "event_id": new_event_id(),
        "event_type": "DELIVERED",
        "package_id": package_id,
        "route_id": credential["route_id"],
        "stop_id": "S-014",
        "timestamp": "2026-06-16T18:42:11Z",
        "gps_precision_bucket": "within_50m",
        "proof": {"photo_hash": "fake", "requirements_met": True},
        "device_id": credential["device_id"],
    }
    return sign_delivery_event(unsigned, device, credential, prior)


def test_valid_chain(seeded_route):
    credential = seeded_route["credential"]
    first = _make_event(seeded_route, package_id=seeded_route["packages"][0]["package_id"])
    ok, reason = verify_delivery_event(first, route_credential=credential)
    assert ok, reason

    second = _make_event(seeded_route, package_id=seeded_route["packages"][1]["package_id"], prior=first)
    ok, reason = verify_delivery_event(second, route_credential=credential, prior_event=first)
    assert ok, reason


def test_broken_previous_hash(seeded_route):
    credential = seeded_route["credential"]
    event = _make_event(seeded_route)
    event["previous_event_hash"] = "tampered"
    ok, reason = verify_delivery_event(event, route_credential=credential)
    assert not ok
    assert reason == "invalid_signature"

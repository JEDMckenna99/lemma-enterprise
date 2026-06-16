from crypto.verifier import verify_package_against_route, verify_route_credential


def test_verify_route_and_package(seeded_route, sample_assignment):
    credential = seeded_route["credential"]
    ok, reason = verify_route_credential(credential, device_id="DEVICE-001")
    assert ok, reason

    ok, reason, policy = verify_package_against_route(sample_assignment, credential)
    assert ok, reason
    assert "photo_required" in policy


def test_device_mismatch(seeded_route):
    credential = seeded_route["credential"]
    ok, reason = verify_route_credential(credential, device_id="OTHER")
    assert not ok
    assert reason == "device_mismatch"

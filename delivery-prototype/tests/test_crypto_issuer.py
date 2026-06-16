from crypto.device_keys import ensure_issuer_keypair, load_public_key_b64, sign_bytes, verify_bytes
from crypto.issuer import issue_route_credential
from config import ISSUER_KEY_PATH


def test_route_credential_signs_and_verifies(temp_db):
    issuer = ensure_issuer_keypair(ISSUER_KEY_PATH)
    from crypto.device_keys import ensure_device_keypair
    from config import DEVICE_KEY_PATH

    device = ensure_device_keypair(DEVICE_KEY_PATH)
    credential = issue_route_credential(
        issuer,
        route_id="R-001",
        driver_id="D-1",
        device_id="DEVICE-001",
        device_pubkey=load_public_key_b64(device),
        stops=["S-1"],
        packages=[{"package_id": "P-1", "stop_id": "S-1", "policy": {"photo_required": True}}],
        policy_defaults={"photo_required": True, "signature_required": False, "otp_required": False},
    )
    import hashlib
    from crypto.canonical import canonical_json_bytes

    message = hashlib.sha256(canonical_json_bytes(credential)).digest()
    assert verify_bytes(credential["issuer_pubkey"], message, credential["signature"])

    tampered = dict(credential)
    tampered["driver_id"] = "EVIL"
    bad_message = hashlib.sha256(canonical_json_bytes(tampered)).digest()
    assert not verify_bytes(tampered["issuer_pubkey"], bad_message, tampered["signature"])

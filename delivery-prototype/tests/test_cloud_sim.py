import time


def test_cloud_good(client):
    t0 = time.perf_counter()
    res = client.post("/api/cloud/confirm", json={"package_id": "P-1", "network_profile": "good"})
    elapsed = time.perf_counter() - t0
    assert res.status_code == 200
    assert res.get_json()["allowed"] is True
    assert elapsed >= 0.4


def test_cloud_offline(client):
    res = client.post("/api/cloud/confirm", json={"package_id": "P-1", "network_profile": "offline"})
    assert res.status_code == 503


def test_cloud_timeout(client):
    res = client.post("/api/cloud/confirm", json={"package_id": "P-1", "network_profile": "timeout"})
    assert res.status_code == 504

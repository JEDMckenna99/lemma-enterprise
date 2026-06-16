from scripts.run_benchmark import run_cloud, run_local


def test_benchmark_harness_local():
    result = run_local(3)
    assert result["mode"] == "local-first"
    assert result["avg_sec"] >= 0
    assert result["failure_rate"] == 0.0


def test_benchmark_harness_cloud(client):
    result = run_cloud(2, "offline")
    assert result["mode"] == "cloud-check"
    assert result["failure_rate"] == 1.0

from monitoring import request_telemetry


def test_slo_snapshot_tracks_error_rate_and_latency():
    base = 1_700_000_000.0
    request_telemetry._RESPONSE_STATUSES.clear()
    request_telemetry._RESPONSE_LATENCIES_MS.clear()

    request_telemetry.record_response(200, now=base + 1, duration_ms=100)
    request_telemetry.record_response(500, now=base + 2, duration_ms=900)
    request_telemetry.record_response(502, now=base + 3, duration_ms=1200)
    request_telemetry.record_response(200, now=base + 4, duration_ms=300)

    snapshot = request_telemetry.slo_snapshot_last_5m(now=base + 10)
    assert snapshot["responses_5m"] == 4
    assert snapshot["server_5xx_5m"] == 2
    assert snapshot["error_rate_5m_percent"] == 50.0
    assert snapshot["p95_latency_ms_5m"] is not None

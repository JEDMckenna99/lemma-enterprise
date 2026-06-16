import pytest

from models.schemas import MetricsLog, aggregate_metrics, bucket_to_seconds, validate_metrics_payload


def test_bucket_to_seconds():
    assert bucket_to_seconds("6-10_sec") == 8
    assert bucket_to_seconds("failed_retry") == 20


def test_aggregate_metrics():
    logs = [
        {"delayed_action": "scan", "stop_type": "apartment", "signal_quality": "weak", "delay_bucket": "6-10_sec", "retry_needed": True},
        {"delayed_action": "scan", "stop_type": "house", "signal_quality": "good", "delay_bucket": "0-2_sec", "retry_needed": False},
    ]
    out = aggregate_metrics(logs)
    assert out["total_delay_events"] == 2
    assert out["retry_count"] == 1
    assert out["most_common_delayed_action"] == "scan"


def test_reject_sensitive_fields():
    with pytest.raises(ValueError):
        validate_metrics_payload({"package_id": "P-1", "delay_bucket": "0-2_sec"})


def test_metrics_log_from_dict():
    log = MetricsLog.from_dict({
        "route_type": "suburban",
        "stop_type": "apartment",
        "signal_quality": "weak",
        "delayed_action": "confirm_delivery",
        "delay_bucket": "6-10_sec",
        "retry_needed": True,
    })
    assert log.sensitive_data_collected is False

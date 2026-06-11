import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.platform_sites import filter_managed_sites, is_demo_site, is_managed_platform_site


def test_managed_site_allowlist():
    assert is_managed_platform_site("lemma.id") is True
    assert is_managed_platform_site("site_demo_tickets") is True
    assert is_managed_platform_site("site_demo_trials") is True
    assert is_managed_platform_site("lemma_platform") is False
    assert is_managed_platform_site("test_site_xyz_example_com") is False


def test_filter_managed_sites():
    rows = filter_managed_sites(
        [
            {"site_id": "lemma.id", "site_domain": "lemma.id", "created_at": "2026-01-02"},
            {"site_id": "site_demo_tickets", "site_domain": "tickets-demo.lemma.id", "created_at": "2026-01-03"},
            {"site_id": "site_demo_trials", "site_domain": "trials-demo.lemma.id", "created_at": "2026-01-01"},
            {"site_id": "lemma_platform", "site_domain": "lemma.id", "created_at": "2026-01-04"},
            {"site_id": "bootstrap_test", "site_domain": "example.test", "created_at": "2026-01-05"},
        ]
    )
    assert [r["site_id"] for r in rows] == [
        "site_demo_tickets",
        "lemma.id",
        "site_demo_trials",
    ]


def test_demo_site_classification():
    assert is_demo_site("site_demo_tickets") is True
    assert is_demo_site("lemma.id") is False

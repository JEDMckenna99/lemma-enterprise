from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_demo_hub_js_gates_assurance_workflow():
    js = (ROOT / "static" / "js" / "demo" / "ishuman-demo.js").read_text(encoding="utf-8")
    assert "assuranceDemoMode" in js
    assert "DEFAULT_DEMO_SITE_ASSURANCE = 'passkey'" in js
    assert "demoRequiredAssurance" in js
    assert "isSiteVerified" in js
    assert "verifyForBackend" in js
    assert "requiredAssurance" in js
    assert "/api/demo/ishuman/require-ishuman" in js
    assert "/api/demo/ishuman/assurance-status" in js
    assert "passkeyPpids" in js
    assert "updateStepUpCompare" in js


def test_demo_hub_template_has_five_step_assurance_sections():
    html = (ROOT / "templates" / "demo" / "ishuman.html").read_text(encoding="utf-8")
    assert 'id="ih-step-5"' in html
    assert "ih-require-ishuman-btn" in html
    assert "ih-stepup-compare" in html
    assert "assurance-only" in html

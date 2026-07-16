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
    assert "/api/demo/ishuman/site-doubt" in js
    assert "/api/demo/ishuman/clear-site-doubt" in js
    assert "/api/demo/ishuman/assurance-status" in js
    assert "passkeyPpids" in js
    assert "ticketsRequiresIshuman" in js
    assert "renderLifecyclePanel" in js
    assert "renderPresentationInspector" in js
    assert "MAIN_WORKFLOW_STEPS" in js
    assert "verifyFreshForBackend" in js


def test_demo_hub_template_has_three_concept_lifecycle():
    html = (ROOT / "templates" / "demo" / "lemma.html").read_text(encoding="utf-8")
    for step in range(1, 4):
        assert f'id="ih-step-{step}"' in html
    assert 'id="ih-step-4"' not in html
    assert 'id="ih-step-5"' not in html
    assert 'id="ih-lifecycle-panel"' in html
    assert 'id="ih-quick-progress"' in html
    assert 'id="ih-presentation-inspector"' in html
    assert 'id="ih-presentation-fields"' in html
    assert 'id="ih-create-doubt-btn"' in html
    assert 'id="ih-resolve-doubt-btn"' in html
    assert 'id="ih-step-human"' in html
    assert 'id="ih-human-cta"' not in html
    assert 'id="ih-step-rotation"' not in html
    assert "ih-stepup-compare" in html
    assert "ih-simulate-rotation-btn" not in html
    assert "assurance-only" in html
    assert 'data-quick-act="3"' in html
    assert "Enforce site decisions" in html
    assert "Developer view: signed presentations" in html


def test_demo_hub_css_supports_lifecycle_and_inspector():
    css = (ROOT / "static" / "css" / "demo" / "ishuman-demo.css").read_text(encoding="utf-8")
    assert ".demo-lifecycle-panel" in css
    assert ".demo-presentation-inspector" in css
    assert ".demo-progress" in css

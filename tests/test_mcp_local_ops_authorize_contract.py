from pathlib import Path


def test_mcp_runtime_has_local_ops_gate_contract():
    source = Path("mcp-server/index.js").read_text(encoding="utf-8")
    assert "LEMMA_ENABLE_LOCAL_OPS_GATE" in source
    assert "operationDescriptorForTool" in source
    assert "runtimeAuthorizeDescriptor" in source
    assert "/api/wallet/runtimes/" in source
    assert "X-Lemma-Credential" in source


def test_mcp_runtime_maps_actions_for_api_and_browser():
    source = Path("mcp-server/index.js").read_text(encoding="utf-8")
    assert "api.call.write" in source
    assert "api.call.read" in source
    assert "api.internal.admin" in source
    assert "browser.interact" in source
    assert "browser.read" in source

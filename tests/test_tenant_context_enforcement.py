import os
import sys

from flask import Flask, g

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from auth.decorators import _set_tenant_context_from_request
from api.agent_credentials import _enforce_agent_tenant_context
from api.developer_api import _enforce_developer_tenant_context
from api.site_management_api import _enforce_site_tenant_context


def test_auth_decorator_tenant_context_normalizes_and_falls_back():
    app = Flask(__name__)
    with app.test_request_context("/tenant?org_id=Acme-Prod_1&environment=not-valid"):
        _set_tenant_context_from_request()
        assert g.org_id == "acme-prod_1"
        assert g.environment == "prod"


def test_developer_tenant_scope_forbidden_on_site_mismatch():
    app = Flask(__name__)
    with app.test_request_context(
        "/api/developer/sites/site-a/keys",
        headers={"X-Lemma-Site-Id": "site-b", "X-Lemma-Org-Id": "Org_A", "X-Lemma-Environment": "staging"},
    ):
        from flask import request

        request.view_args = {"site_id": "site-a"}
        response = _enforce_developer_tenant_context()
        assert response is not None
        body, status = response
        assert status == 403
        assert body.get_json().get("error") == "site_scope_forbidden"


def test_site_management_tenant_scope_forbidden_on_site_mismatch():
    app = Flask(__name__)
    with app.test_request_context(
        "/api/developer/sites/site-a/users",
        headers={"X-Lemma-Site-Id": "site-z", "X-Lemma-Org-Id": "tenant-1", "X-Lemma-Environment": "dev"},
    ):
        from flask import request

        request.view_args = {"site_id": "site-a"}
        response = _enforce_site_tenant_context()
        assert response is not None
        body, status = response
        assert status == 403
        assert body.get_json().get("error") == "site_scope_forbidden"


def test_agent_credentials_tenant_context_sets_defaults():
    app = Flask(__name__)
    with app.test_request_context("/api/agent/credentials"):
        _enforce_agent_tenant_context()
        assert g.org_id == "org_default"
        assert g.environment == "prod"


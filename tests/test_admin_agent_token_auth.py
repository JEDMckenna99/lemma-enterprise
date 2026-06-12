"""Admin API accepts lemma.id-bound agent tokens with admin scope."""

from __future__ import annotations

from flask import Flask

from auth.agent_principal import extract_agent_admin_principal


def test_extract_agent_admin_principal_success(monkeypatch):
    monkeypatch.setattr(
        'api.agent_credentials.validate_agent_token_with_reason',
        lambda token: (
            {
                'authorized_by_ppid': 'did:lemma:ppid_' + ('a' * 64),
                'token_id': 'tok_test_1',
                'scope': ['read', 'admin'],
                'allowed_sites': ['lemma.id'],
                'allowed_paths': ['/api/admin/**'],
            },
            None,
        ),
    )
    monkeypatch.setattr(
        'api.agent_credentials.check_path_allowed',
        lambda path, patterns: True,
    )

    principal, error, info = extract_agent_admin_principal(
        {'X-Agent-Token': 'lm_agent_testtoken'},
        request_path='/api/admin/trust/queue',
    )
    assert error is None
    assert principal is not None
    assert principal.site_binding == 'lemma.id'
    assert 'admin' in principal.scope
    assert info['token_id'] == 'tok_test_1'


def test_extract_agent_admin_principal_rejects_non_lemma_site(monkeypatch):
    monkeypatch.setattr(
        'api.agent_credentials.validate_agent_token_with_reason',
        lambda token: (
            {
                'authorized_by_ppid': 'did:lemma:ppid_' + ('a' * 64),
                'token_id': 'tok_test_2',
                'scope': ['read', 'admin'],
                'allowed_sites': ['customer.example.com'],
                'allowed_paths': ['/api/admin/**'],
            },
            None,
        ),
    )

    principal, error, _info = extract_agent_admin_principal(
        {'X-Agent-Token': 'lm_agent_testtoken'},
        request_path='/api/admin/trust/queue',
    )
    assert principal is None
    assert error == 'agent_site_binding_mismatch'


def test_admin_route_accepts_agent_token(monkeypatch):
    from api.dashboard_api import dashboard_bp

    monkeypatch.setattr(
        'auth.decorators.extract_user_lemma_principal',
        lambda headers: (None, 'missing_lemma_header'),
    )
    monkeypatch.setattr(
        'auth.agent_principal.extract_agent_admin_principal',
        lambda headers, request_path=None: (
            type('P', (), {
                'ppid': 'did:lemma:ppid_' + ('a' * 64),
                'credential_id': 'tok_test_1',
                'permission_id': 'admin_access',
                'scope': ['admin', 'read'],
                'site_binding': 'lemma.id',
                'auth_method': 'agent_token',
            })(),
            None,
            {'token_id': 'tok_test_1'},
        ),
    )
    monkeypatch.setattr('api.dashboard_api._load_admin_sites', lambda: [])

    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(dashboard_bp)

    with app.test_client() as client:
        resp = client.get(
            '/api/admin/sites',
            headers={'X-Agent-Token': 'lm_agent_testtoken'},
        )
        assert resp.status_code == 200

"""
Shared credential formatting helpers for site-scoped permission lemmas.
"""

from copy import deepcopy
from typing import Dict, Any


def normalize_site_permission_lemma(
    credential: Dict[str, Any],
    site_id: str,
    site_domain: str,
    permission_id: str,
) -> Dict[str, Any]:
    """
    Enforce a uniform site-lemma envelope across issuance paths.

    This keeps the lemma shape consistent for platform-issued and site-issued
    credentials. The effective authorization difference should come from the
    permission itself (permissionId/scope), not schema drift.
    """
    normalized = deepcopy(credential or {})
    normalized['type'] = ['VerifiableCredential', 'PermissionLemma']
    normalized['packageType'] = 'permission'

    existing_cs = normalized.get('credentialSubject')
    existing_claims = normalized.get('claims')

    if isinstance(existing_cs, dict):
        credential_subject = dict(existing_cs)
    elif isinstance(existing_claims, dict):
        credential_subject = dict(existing_claims)
    else:
        credential_subject = {}

    if isinstance(existing_claims, dict):
        claims = dict(existing_claims)
    else:
        claims = dict(credential_subject)

    core_fields = {
        'packageType': 'permission',
        'siteId': site_id,
        'siteDomain': site_domain,
        'permissionId': permission_id,
    }

    credential_subject.update(core_fields)
    claims.update(core_fields)

    normalized['credentialSubject'] = credential_subject
    normalized['claims'] = claims
    return normalized


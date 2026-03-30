"""
Access token auth has been removed in the local-first auth transition.
All authentication now uses signed credentials via X-Lemma-Credential.
"""
import pytest

pytestmark = pytest.mark.skip(
    reason="Access token auth removed in local-first transition; all auth uses signed credentials"
)


def test_placeholder():
    pass

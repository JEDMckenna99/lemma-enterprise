import json

from scripts import lemma_firewall


def test_parse_scope_handles_list_string_encoding():
    credential = {
        "credentialSubject": {
            "scope": "['developer', 'write', 'read']",
        }
    }
    parsed = lemma_firewall._parse_scope_from_lemma_credential(json.dumps(credential))  # pylint: disable=protected-access
    assert parsed == {"developer", "write", "read"}


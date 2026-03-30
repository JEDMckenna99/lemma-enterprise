# lemma-auth-flask

Flask middleware scaffold for verifying `X-Lemma-Credential` headers and enforcing route scope/site policies.

## Quick usage

```python
from flask import Flask
from lemma_auth_flask import LemmaAuth

app = Flask(__name__)
lemma_auth = LemmaAuth(required_site="example.com")

@app.get("/api/private")
@lemma_auth.require_lemma(scope="read", site_bound=True)
def private_route():
    return {"ok": True}
```


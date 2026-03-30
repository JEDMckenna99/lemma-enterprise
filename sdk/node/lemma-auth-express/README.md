# @lemma/auth-express

Express middleware scaffold for verifying `X-Lemma-Credential` headers and enforcing scope/site policy.

## Usage

```js
const express = require("express");
const { createLemmaAuth } = require("@lemma/auth-express");

const app = express();
const lemma = createLemmaAuth({
  requiredSite: "example.com",
  verifyCredential: async (credential) => ({ valid: true }),
});

app.use(lemma.attachPrincipal());
app.get("/api/private", lemma.requireLemma({ scope: "read", siteBound: true }), (req, res) => {
  res.json({ ok: true, ppid: req.lemmaPrincipal.ppid });
});
```

## TypeScript

This package ships typed surfaces via `index.d.ts`.

```ts
import { createLemmaAuth, LemmaErrorPayload } from "@lemma/auth-express";

const lemma = createLemmaAuth({
  requiredSite: "example.com",
  verifyCredential: async (credential) => ({ valid: true }),
});

const requireWrite = lemma.requireLemma({ scope: "write", siteBound: true });

// Example of typed error shape on deny paths
const denied: LemmaErrorPayload = {
  success: false,
  error: "missing_scope",
  message: "Insufficient scope",
};
```


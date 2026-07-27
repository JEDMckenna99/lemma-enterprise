/**
 * Minimal Express T2 signup example using @lemma.id/proof-verifier (Section 10).
 */
import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const pkgRoot = path.resolve(__dirname, "../../packages/proof-verifier-js/index.mjs");
const { createVerifier } = await import(pkgRoot);

const app = express();
app.use(express.json({ limit: "256kb" }));

const SITE_ID = process.env.SITE_ID || "app.example.com";
const REQUIRED = process.env.REQUIRED_ASSURANCE || "ishuman";
const verifier = createVerifier({ siteId: SITE_ID, requiredAssurance: REQUIRED });

app.post("/api/signup", async (req, res) => {
  const presentation = req.body?.presentation;
  if (!presentation) {
    return res.status(400).json({ success: false, reason: "presentation_missing" });
  }
  const result = await verifier.verify(presentation);
  if (!result.ok) {
    return res.status(401).json({ success: false, reason: result.reason });
  }
  return res.json({ success: true, ppid: result.ppid, assurance: result.assurance });
});

const port = Number(process.env.PORT || 5051);
app.listen(port, () => console.log(`express signup example on :${port}`));

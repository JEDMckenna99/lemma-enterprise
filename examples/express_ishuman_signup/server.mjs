/**
 * Sign in with lemma.id — Express example with session cookies.
 */
import crypto from "node:crypto";
import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const pkgRoot = path.resolve(__dirname, "../../packages/proof-verifier-js/index.mjs");
const { createVerifier } = await import(pkgRoot);

const app = express();
app.use(express.json({ limit: "256kb" }));

const SITE_ID = process.env.SITE_ID || "localhost";
const REQUIRED = process.env.REQUIRED_ASSURANCE || "passkey";
const SESSION_SECRET = process.env.SESSION_SECRET || "dev-change-me";
const SESSION_COOKIE = "lemma_example_session";
const verifier = createVerifier({ siteId: SITE_ID, requiredAssurance: REQUIRED });
const users = new Map();

function signSession(ppid) {
  const payload = { ppid, exp: Math.floor(Date.now() / 1000) + 86400 };
  const raw = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const sig = crypto.createHmac("sha256", SESSION_SECRET).update(raw).digest("hex");
  return `${raw}.${sig}`;
}

function readSession(token) {
  if (!token || !token.includes(".")) return null;
  const [raw, sig] = token.split(".");
  const expected = crypto.createHmac("sha256", SESSION_SECRET).update(raw).digest("hex");
  if (!crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(sig))) return null;
  try {
    const payload = JSON.parse(Buffer.from(raw, "base64url").toString("utf8"));
    if (payload.exp < Math.floor(Date.now() / 1000)) return null;
    return payload.ppid || null;
  } catch {
    return null;
  }
}

function findOrCreateUser(ppid) {
  if (!users.has(ppid)) users.set(ppid, { ppid, createdAt: Date.now() });
  return users.get(ppid);
}

function parseCookie(header, name) {
  if (!header) return null;
  const part = header.split(";").map((c) => c.trim()).find((c) => c.startsWith(`${name}=`));
  return part ? decodeURIComponent(part.split("=").slice(1).join("=")) : null;
}

function requireAuth(req, res, next) {
  const ppid = readSession(parseCookie(req.headers.cookie, SESSION_COOKIE));
  if (!ppid) return res.status(401).json({ success: false, error: "auth_required" });
  req.ppid = ppid;
  return next();
}

const loginPage = `<!doctype html>
<html><head><title>Sign in with lemma.id (Express)</title></head><body>
<h1>Sign in with lemma.id</h1>
<p id="status">Loading…</p>
<button id="signin" type="button" style="display:none">Sign in with lemma.id</button>
<script src="https://lemma.id/sdk/proof-verifier.js"></script>
<script>
const SITE_ID = ${JSON.stringify(SITE_ID)};
const REQUIRED = ${JSON.stringify(REQUIRED)};
const statusEl = document.getElementById('status');
const btn = document.getElementById('signin');
async function refresh() {
  const me = await fetch('/api/me', { credentials: 'include' });
  if (me.ok) { statusEl.textContent = 'Signed in as ' + (await me.json()).ppid; btn.style.display='none'; return; }
  statusEl.textContent = 'Not signed in'; btn.style.display='inline-block';
}
btn.onclick = async () => {
  btn.disabled = true;
  try {
    const verifier = new ProofVerifier({ siteId: SITE_ID });
    const { ok, presentation, reason } = await verifier.verifyForBackend({ autoProvision: true, requiredAssurance: REQUIRED });
    if (!ok) throw new Error(reason || 'not_verified');
    const resp = await fetch('/api/login', { method:'POST', credentials:'include', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ presentation }) });
    if (!resp.ok) throw new Error('server_denied');
    await refresh();
  } catch (e) { statusEl.textContent = e.message; btn.disabled = false; }
};
refresh();
</script>
<p><a href="/logout">Logout</a></p>
</body></html>`;

app.get("/", (_req, res) => {
  res.type("html").send(loginPage);
});

app.get("/api/me", requireAuth, (req, res) => {
  res.json({ success: true, ppid: req.ppid });
});

app.post("/api/login", async (req, res) => {
  const presentation = req.body?.presentation;
  if (!presentation) return res.status(400).json({ success: false, reason: "presentation_missing" });
  const result = await verifier.verify(presentation);
  if (!result.ok) return res.status(401).json({ success: false, reason: result.reason });
  findOrCreateUser(result.ppid);
  res.cookie(SESSION_COOKIE, signSession(result.ppid), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 86400000,
  });
  return res.json({ success: true, ppid: result.ppid, assurance: result.assurance });
});

app.get("/logout", (_req, res) => {
  res.clearCookie(SESSION_COOKIE);
  res.redirect("/");
});

const port = Number(process.env.PORT || 5051);
app.listen(port, () => console.log(`express login example on :${port}`));

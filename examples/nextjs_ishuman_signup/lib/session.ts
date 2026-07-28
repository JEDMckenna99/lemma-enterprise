import crypto from "node:crypto";

const SESSION_COOKIE = "lemma_example_session";
const SESSION_SECRET = process.env.SESSION_SECRET || "dev-change-me";

export function signSession(ppid: string): string {
  const payload = { ppid, exp: Math.floor(Date.now() / 1000) + 86400 };
  const raw = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const sig = crypto.createHmac("sha256", SESSION_SECRET).update(raw).digest("hex");
  return `${raw}.${sig}`;
}

export function readSession(token: string | undefined): string | null {
  if (!token || !token.includes(".")) return null;
  const [raw, sig] = token.split(".");
  const expected = crypto.createHmac("sha256", SESSION_SECRET).update(raw).digest("hex");
  try {
    if (!crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(sig))) return null;
  } catch {
    return null;
  }
  try {
    const payload = JSON.parse(Buffer.from(raw, "base64url").toString("utf8")) as { ppid?: string; exp?: number };
    if ((payload.exp || 0) < Math.floor(Date.now() / 1000)) return null;
    return payload.ppid || null;
  } catch {
    return null;
  }
}

export { SESSION_COOKIE };

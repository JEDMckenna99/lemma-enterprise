import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const pkgRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../packages/proof-verifier-js/index.mjs",
);

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let verifierPromise: Promise<any> | null = null;

export async function getVerifier() {
  if (!verifierPromise) {
    verifierPromise = import(pkgRoot).then(({ createVerifier }) =>
      createVerifier({
        siteId: process.env.SITE_ID || "localhost",
        requiredAssurance: (process.env.REQUIRED_ASSURANCE || "passkey") as "passkey" | "ishuman",
      }),
    );
  }
  return verifierPromise;
}

const users = new Map<string, { ppid: string; createdAt: number }>();

export function findOrCreateUser(ppid: string) {
  if (!users.has(ppid)) users.set(ppid, { ppid, createdAt: Date.now() });
  return users.get(ppid)!;
}

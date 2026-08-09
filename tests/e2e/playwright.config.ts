import { defineConfig } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

// Chrome treats http://localhost as a secure context and will run WebAuthn
// there; http://127.0.0.1 is an IP, so passkey ceremonies fail. Both resolve to
// RP ID "localhost" on the client and the server, so the host must be the name.
const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5000';

// Device enrollment spans two requests (device-enroll/begin then /complete) and
// the dev server is threaded, so an in-memory SQLite would hand each thread its
// own empty database. Use a file the whole process shares.
const tmpDir = path.join(__dirname, '.tmp');
fs.mkdirSync(tmpDir, { recursive: true });
const dbPath = path.join(tmpDir, 'e2e.db').replace(/\\/g, '/');

export default defineConfig({
  testDir: '.',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['list']] : [['list']],
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command: 'python app.py',
        cwd: '../..',
        url: `${baseURL}/link`,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
        env: {
          ...process.env,
          // DEBUG is what makes app.py create the tables on boot.
          FLASK_ENV: 'development',
          SESSION_SECRET: 'test-session-secret',
          DATABASE_URL: `sqlite:///${dbPath}`,
          LEMMA_PPID_ROOT_KEY: 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
          LEMMA_IDENTITY_ROOT_PEPPER_V1: 'yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy',
          LEMMA_PERSON_ROOT_SALT_V1: 'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz',
          LEMMA_ALLOW_DEV_ORIGINS: '1',
          // Site proofs are signed credentials even at the passkey tier, so the
          // popup flow needs an issuer. This is the in-memory dev one, not KMS.
          LEMMA_DEV_INSECURE_ISSUER: '1',
        },
      },
});

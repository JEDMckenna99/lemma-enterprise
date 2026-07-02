import { defineConfig } from '@playwright/test';

const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5000';

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
          SESSION_SECRET: 'test-session-secret',
          DATABASE_URL: 'sqlite:///:memory:',
          LEMMA_PPID_ROOT_KEY: 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
          LEMMA_IDENTITY_ROOT_PEPPER_V1: 'yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy',
          LEMMA_PERSON_ROOT_SALT_V1: 'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz',
        },
      },
});

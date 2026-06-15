import { defineConfig, devices } from "@playwright/test";

// Smoke tests for the operator console. The backend (REST :8000) must be running
// separately; this config starts the UI itself. Locally, a dev server already on
// :3007 is reused; in CI, `npm run start` serves the production build.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "list" : "line",
  use: {
    baseURL: "http://localhost:3007",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run start",
    url: "http://localhost:3007/login",
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
  },
});

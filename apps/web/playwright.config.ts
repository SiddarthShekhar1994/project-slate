import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

const ROOT = path.resolve(__dirname, "../..");

/**
 * End-to-end tests. They start the API and the web app unless they are
 * already running. Postgres must be up with the schema migrated
 * (`uv run alembic -c apps/api/alembic.ini upgrade head`).
 *
 * In environments with a preinstalled Chromium, set PW_CHROMIUM_PATH to it
 * instead of running `playwright install`.
 */
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60_000,
  fullyParallel: false,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } } },
    { name: "phone", use: { ...devices["Pixel 7"], browserName: "chromium" } },
  ],
  webServer: [
    {
      command: "uv run uvicorn slate_api.main:app --host 127.0.0.1 --port 8000",
      cwd: ROOT,
      // The silent voice and fake transcriber let audio paths be tested without API keys.
      env: { TTS_PROVIDER: process.env.TTS_PROVIDER ?? "silent", STT_PROVIDER: process.env.STT_PROVIDER ?? "fake" },
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: "pnpm dev --port 3000",
      url: "http://127.0.0.1:3000/login",
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});

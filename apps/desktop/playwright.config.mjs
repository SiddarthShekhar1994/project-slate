import { defineConfig } from "@playwright/test";

// Drives the real desktop app through Playwright's Electron support. By default
// it launches from source (backend via uv, interface via SLATE_WEB_DIR or
// next dev); set SLATE_APP_PATH to an installed or unpacked Slate executable
// to test the packaged app, as the Windows build does.
export default defineConfig({
  testDir: "tests",
  timeout: 300_000,
  workers: 1,
  reporter: [["list"]],
});

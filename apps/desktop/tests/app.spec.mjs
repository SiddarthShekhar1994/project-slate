import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron, expect, test } from "@playwright/test";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..", "..");

function backendProcesses() {
  if (process.platform === "win32") {
    const out = execFileSync("tasklist", ["/FI", "IMAGENAME eq slate-api.exe", "/NH"]).toString();
    return out.split("\n").filter((line) => line.toLowerCase().includes("slate-api.exe")).length;
  }
  try {
    return execFileSync("pgrep", ["-f", "slate_api.desktop|slate-api --port"]).toString().trim().split("\n").length;
  } catch {
    return 0; // pgrep exits 1 when nothing matches
  }
}

/** Answer keys straight from the app's SQLite file, as the web end-to-end tests do with Postgres. */
function keysFor(dataDir, worksheetId) {
  const out = execFileSync("uv", ["run", "--quiet", "python", "scripts/e2e_keys.py", worksheetId], {
    cwd: REPO,
    env: { ...process.env, DATABASE_URL: `sqlite:///${path.join(dataDir, "slate.db").replaceAll("\\", "/")}` },
    stdio: ["ignore", "pipe", "inherit"],
  }).toString();
  return JSON.parse(out.split("\n").find((line) => line.startsWith("[")));
}

test("starts without sign-in, grades answers, and leaves nothing running when closed", async () => {
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), "slate-desktop-test-"));
  const args = process.env.SLATE_APP_PATH ? [] : [path.join(HERE, "..")];
  if (process.platform === "linux" && process.getuid?.() === 0) args.push("--no-sandbox");
  const app = await electron.launch({
    executablePath: process.env.SLATE_APP_PATH || undefined,
    args,
    env: { ...process.env, SLATE_USER_DATA: userData },
    timeout: 120_000,
  });
  const window = await app.firstWindow();

  // First launch creates the database and starts both servers.
  await expect(window.getByRole("heading", { level: 1 })).toContainText("Welcome", { timeout: 240_000 });
  await expect(window).toHaveURL(/127\.0\.0\.1:\d+\/library/);
  await expect(window.getByRole("link", { name: "Settings" }).first()).toBeVisible();
  await expect(window.getByText("Everything stays on this computer.")).toBeVisible();

  await window.getByRole("link", { name: "Settings" }).first().click();
  await expect(window.getByRole("heading", { name: "API keys" })).toBeVisible();
  await expect(window.getByText("Claude: off")).toBeVisible();

  // Practice: grading runs in the sandbox (on Windows, the warm worker pool).
  const id = await window.evaluate(async () => {
    const r = await fetch("/api/practice/worksheets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skill_ids: ["calc1.derivatives.chain_rule"], count: 2 }),
    });
    return (await r.json()).id;
  });
  await window.goto(`${new URL(window.url()).origin}/practice/${id}`);
  const keys = keysFor(path.join(userData, "data"), id);
  const answer = window.getByRole("textbox", { name: "Your answer" });
  await answer.fill(keys[0].wrong);
  await window.getByRole("button", { name: "Check answer" }).click();
  await expect(window.getByText("Not quite")).toBeVisible({ timeout: 30_000 });
  await window.getByRole("button", { name: "Try a similar problem" }).click();
  const retry = keysFor(path.join(userData, "data"), id);
  await window.getByRole("textbox", { name: "Your answer" }).fill(retry[0].key);
  await window.getByRole("button", { name: "Check answer" }).click();
  await expect(window.getByText("Correct", { exact: true })).toBeVisible({ timeout: 30_000 });

  // The database and settings live in the app's data folder.
  expect(fs.existsSync(path.join(userData, "data", "slate.db"))).toBe(true);

  const origin = new URL(window.url()).origin;
  await app.close();
  await expect.poll(backendProcesses, { timeout: 15_000 }).toBe(0);
  await expect
    .poll(async () => fetch(`${origin}/api/health`).then(() => "up", () => "down"), { timeout: 15_000 })
    .toBe("down");
});

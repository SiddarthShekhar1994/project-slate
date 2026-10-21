import { execFileSync } from "node:child_process";
import path from "node:path";
import { type Page, expect } from "@playwright/test";

const ROOT = path.resolve(__dirname, "../../../..");

export type Keys = { position: number; key: string; wrong: string }[];

/** Read answer keys straight from the database (the API never exposes them). */
export function keysFor(worksheetId: string): Keys {
  const out = execFileSync("uv", ["run", "--quiet", "python", "scripts/e2e_keys.py", worksheetId], {
    cwd: ROOT,
    stdio: ["ignore", "pipe", "ignore"],
  }).toString();
  const line = out.split("\n").find((l) => l.startsWith("["));
  if (!line) throw new Error(`no keys for ${worksheetId}: ${out}`);
  return JSON.parse(line);
}

export async function signUp(page: Page) {
  const email = `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}@slate.test`;
  await page.goto("/signup");
  await page.getByLabel("Name").fill("Test Student");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("e2e-password");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/library/);
  return email;
}

export async function newWorksheet(page: Page, skillIds: string[], count = 4): Promise<string> {
  const id = await page.evaluate(async ({ skillIds, count }) => {
    const r = await fetch("/api/practice/worksheets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skill_ids: skillIds, count }),
    });
    return (await r.json()).id as string;
  }, { skillIds, count });
  await page.goto(`/practice/${id}`);
  return id;
}

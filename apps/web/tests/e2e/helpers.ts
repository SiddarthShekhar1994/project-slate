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
  await expect(page).toHaveURL(/\/dashboard/);
  return email;
}

/** Put topics on the student's dashboard by name, as the "Learn a topic" box does. */
export async function addTopics(page: Page, names: string[]) {
  for (const name of names) {
    const status = await page.evaluate(async (topic) => {
      const r = await fetch("/api/topics", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: topic }),
      });
      return r.status;
    }, name);
    expect(status).toBe(201);
  }
}

export const CHAIN_TOPIC = "/topics/calc1.derivatives.chain_rule";

/** The built-in chain rule lesson in the full-size player, opened from its topic's page. */
export async function openChainRuleLesson(page: Page) {
  await page.goto(`${CHAIN_TOPIC}?tab=lesson`);
  await page.getByRole("link", { name: "Open it full size" }).click();
  await expect(page).toHaveURL(/\/lesson\/[0-9a-f-]+/);
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

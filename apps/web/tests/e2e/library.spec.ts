import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { signUp } from "./helpers";

const ROOT = path.resolve(__dirname, "../../../..");

/** A two-page chain rule lecture PDF, written by pymupdf so the test needs no binary fixtures. */
function lecturePdf(): Buffer {
  const script = `
import pymupdf, sys
doc = pymupdf.open()
page = doc.new_page()
page.insert_text((72, 72), "Lecture 7: The chain rule", fontsize=20)
lines = ["The chain rule differentiates a composite function, a function of a function.",
         "If y = f(u) and u = g(x), then dy/dx = dy/du * du/dx.",
         "Example: d/dx sin(x^3 + 1) = cos(x^3 + 1) * 3x^2. The inner function is x^3 + 1."]
for i, line in enumerate(lines):
    page.insert_text((72, 120 + 22 * i), line, fontsize=11)
sys.stdout.buffer.write(doc.tobytes())
`;
  return execFileSync("uv", ["run", "--quiet", "python", "-c", script], { cwd: ROOT });
}

test("upload a lecture, see what it covers, generate a cited lesson", async ({ page }) => {
  await signUp(page);
  await page.goto("/library");
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Choose files" }).click();
  await (await chooser).setFiles({ name: "lecture7_chain_rule.pdf", mimeType: "application/pdf", buffer: lecturePdf() });

  const card = page.getByRole("article", { name: /lecture7[ _]chain[ _]rule|The chain rule/i });
  await expect(card.getByText("Ready")).toBeVisible({ timeout: 30_000 });
  await expect(card.getByText("Chain rule", { exact: true })).toBeVisible();
  await expect(card.getByText("Not used yet")).toBeVisible();

  await page.goto("/lesson");
  await page.getByRole("button", { name: "Chain rule lesson" }).click();
  await expect(page).toHaveURL(/\/lesson\/[0-9a-f-]+/, { timeout: 60_000 });
  await expect(page.getByRole("heading", { name: "Built from" })).toBeVisible();
  await expect(page.getByText(/lecture7|chain rule/i).first()).toBeVisible();

  await page.goto("/library");
  await expect(card.getByRole("link").first()).toBeVisible();
});

test("unsupported files are explained", async ({ page }) => {
  await signUp(page);
  await page.goto("/library");
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Choose files" }).click();
  await (await chooser).setFiles({ name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("hello") });
  await expect(page.getByText(/Slate reads PDF/)).toBeVisible();
});

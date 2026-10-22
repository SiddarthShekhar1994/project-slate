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

test("upload a lecture, see what it covers, get a lesson that cites it", async ({ page }) => {
  await signUp(page);
  await page.goto("/library");
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Choose files" }).click();
  await (await chooser).setFiles({ name: "lecture7_chain_rule.pdf", mimeType: "application/pdf", buffer: lecturePdf() });

  const card = page.getByRole("article", { name: /lecture7[ _]chain[ _]rule|The chain rule/i });
  await expect(card.getByText("Ready")).toBeVisible({ timeout: 30_000 });
  await expect(card.getByText("Not used yet")).toBeVisible();

  // The topic it covers links to that topic's page, where a new lesson is written from the lecture.
  await card.getByRole("link", { name: "Chain rule", exact: true }).click();
  await expect(page).toHaveURL(/\/topics\/calc1\.derivatives\.chain_rule/);
  await page.getByRole("link", { name: "Lesson", exact: true }).click();
  await page.getByRole("button", { name: "Write a new lesson" }).click();
  await expect(page.getByText(/Built from .*(lecture7|chain rule)/i)).toBeVisible({ timeout: 60_000 });

  await page.goto("/library");
  await expect(card.getByText("Ready")).toBeVisible();
  await expect(card.getByText("Not used yet")).toHaveCount(0);
});

test("unsupported files are explained", async ({ page }) => {
  await signUp(page);
  await page.goto("/library");
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Choose files" }).click();
  await (await chooser).setFiles({ name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("hello") });
  await expect(page.getByText(/Slate reads PDF/)).toBeVisible();
});

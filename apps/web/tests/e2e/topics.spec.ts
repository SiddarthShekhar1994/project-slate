import { expect, test } from "@playwright/test";
import { signUp } from "./helpers";

test("a topic picked on the dashboard gets its own tab: lesson, problems, worksheets", async ({ page }) => {
  await signUp(page);
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { name: "Learn a topic" })).toBeVisible();
  await expect(main.getByText(/No topics yet/)).toBeVisible();

  // Without a Claude key, a topic Slate doesn't have built in says what it needs.
  await page.getByLabel("What are you working on?").fill("related rates");
  await main.getByRole("button", { name: "Add", exact: true }).click();
  await expect(main.getByRole("alert").filter({ hasText: /needs a Claude API key/ })).toBeVisible();

  // A built-in one works right away.
  await main.getByRole("button", { name: "Chain rule", exact: true }).click();
  await expect(main.getByText(/lesson and problems are ready/)).toBeVisible();
  const tile = main.getByRole("article").filter({ hasText: "Chain rule" });
  await expect(tile.getByText("Lesson ready")).toBeVisible();

  // Its lesson plays right on its page.
  await tile.getByRole("link", { name: /^Lesson ?: Chain rule$/ }).click();
  await expect(page).toHaveURL(/\/topics\/calc1\.derivatives\.chain_rule\?tab=lesson/);
  await expect(page.getByRole("heading", { level: 1, name: "Chain rule" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "The chain rule" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Play" })).toBeVisible();

  // Problems: practice straight from here, and the worksheet links back.
  await page.getByRole("link", { name: "Problems", exact: true }).click();
  await expect(page).toHaveURL(/tab=problems/);
  await page.getByRole("button", { name: "Practice, easy to hard" }).click();
  await expect(page).toHaveURL(/\/practice\/[0-9a-f-]+/);
  await page.getByRole("link", { name: /Practice · Chain rule/ }).click();
  await expect(page).toHaveURL(/tab=worksheets/);

  // Worksheets: pick a length and go; the last one is listed.
  await expect(main.getByText(/Chain rule practice/).first()).toBeVisible();
  await page.getByRole("radio", { name: "5" }).check({ force: true });
  await page.getByRole("button", { name: "Start the worksheet" }).click();
  await expect(page).toHaveURL(/\/practice\/[0-9a-f-]+/);
  await expect(page.getByText(/^5 problems, easy to hard/)).toBeVisible();
});

test("a topic can come off the dashboard and back", async ({ page }) => {
  await signUp(page);
  const main = page.getByRole("main");
  await main.getByRole("button", { name: "Product rule", exact: true }).click();
  await expect(main.getByRole("article").filter({ hasText: "Product rule" })).toBeVisible();

  await page.goto("/topics/calc1.derivatives.product_rule");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Remove from dashboard" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await expect(main.getByText(/No topics yet/)).toBeVisible();

  // Its page still opens from a link, and can put it back.
  await page.goto("/topics/calc1.derivatives.product_rule");
  await page.getByRole("button", { name: "Add to your topics" }).click();
  await expect(page.getByRole("button", { name: "Remove from dashboard" })).toBeVisible();
});

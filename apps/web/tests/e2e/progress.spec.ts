import { expect, test } from "@playwright/test";
import { keysFor, newWorksheet, signUp } from "./helpers";

const POWER = "calc1.derivatives.power_rule";
const CHAIN = "calc1.derivatives.chain_rule";

test("progress shows the skill map, mistakes and review queue after practice", async ({ page }) => {
  await signUp(page);
  const id = await newWorksheet(page, [POWER], 2);
  const keys = keysFor(id);
  const answer = page.getByRole("textbox", { name: "Your answer" });
  await answer.fill(keys[0].wrong);
  await page.getByRole("button", { name: "Check answer" }).click();
  await expect(page.getByText("Not quite")).toBeVisible();
  await page.getByRole("button", { name: "Try a similar problem" }).click();
  const retry = keysFor(id);
  await page.getByRole("textbox", { name: "Your answer" }).fill(retry[0].key);
  await page.getByRole("button", { name: "Check answer" }).click();
  await expect(page.getByText("Correct", { exact: true })).toBeVisible();

  await page.goto("/progress");
  await expect(page.getByRole("heading", { name: "Skill map" })).toBeVisible();
  const meter = page.getByRole("meter", { name: "Power rule mastery" });
  await expect(meter).toHaveAttribute("aria-valuenow", /\d+/);
  await expect(page.getByRole("heading", { name: "Mistakes you make most" })).toBeVisible();
  await expect(page.getByText(/1 time/)).toBeVisible();
  const queue = page.getByRole("complementary", { name: "Review queue" });
  await expect(queue.getByText("Coming up this week")).toBeVisible();
  await expect(queue.getByText("Power rule")).toBeVisible();
});

test("a timed exam is graded at hand-in", async ({ page }) => {
  await signUp(page);
  await page.goto(`/progress/exam?skills=${POWER}&count=4&pace=exam`);
  await expect(page.getByRole("checkbox", { name: /Power rule/ })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: /Chain rule/ })).not.toBeChecked();
  await expect(page.getByText("4 problems", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/\d+ minutes/).first()).toBeVisible();
  await page.getByRole("button", { name: "Start the exam" }).click();
  await expect(page).toHaveURL(/\/exam\/[0-9a-f-]+/);
  await expect(page.getByRole("timer", { name: "Time left" })).toHaveText(/\d+:\d\d/);

  const examId = page.url().split("/exam/")[1];
  const keys = keysFor(examId);
  await page.getByLabel("Your answer to problem 1").fill(keys[0].key);
  await page.getByRole("button", { name: "Save answer" }).first().click();
  await expect(page.getByText("Saved.", { exact: true })).toBeVisible();
  await page.getByLabel("Your answer to problem 2").fill(keys[1].wrong);
  await page.getByRole("button", { name: "Save answer" }).first().click();
  await expect(page.getByText("Saved.", { exact: true })).toHaveCount(2);

  await page.getByRole("button", { name: "Hand in", exact: true }).click();
  await page.getByRole("button", { name: "Hand in with 2 blank" }).click();
  await expect(page.getByRole("heading", { name: "1 of 4 right" })).toBeVisible();
  await expect(page.getByText("Where to look:").first()).toBeVisible();
  await expect(page.getByText("Left blank").first()).toBeVisible();

  await page.getByRole("button", { name: "Practice what you missed" }).click();
  await expect(page).toHaveURL(/\/practice\/[0-9a-f-]+/);
});

test("study pace runs through practice with a visible clock", async ({ page }) => {
  await signUp(page);
  await page.goto(`/progress/exam?skills=${CHAIN}&count=4&pace=study`);
  await expect(page.getByRole("radio", { name: /Study pace/ })).toBeChecked();
  await page.getByRole("button", { name: "Start the exam" }).click();
  await expect(page).toHaveURL(/\/practice\/[0-9a-f-]+/);
  await expect(page.getByRole("timer")).toHaveText(/\d+:\d\d/);
  await expect(page.getByRole("button", { name: /Show a hint/ })).toBeVisible();
});

test("formula sheet follows the chosen topics", async ({ page }) => {
  await signUp(page);
  await page.goto(`/progress/formulas?skills=${CHAIN}`);
  await expect(page.getByRole("heading", { name: "Formula sheet" })).toBeVisible();
  await expect(page.getByRole("term").filter({ hasText: "Chain rule" })).toBeVisible();
  await expect(page.getByRole("term").filter({ hasText: "Power rule" })).toHaveCount(0);
  await page.getByRole("checkbox", { name: "Power rule" }).check();
  await expect(page.getByRole("term").filter({ hasText: "Power rule" })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`skills=${CHAIN.replace(/\./g, "\\.")}(%2C|,)${POWER.replace(/\./g, "\\.")}`));
  await expect(page.locator(".katex").first()).toBeVisible();
});

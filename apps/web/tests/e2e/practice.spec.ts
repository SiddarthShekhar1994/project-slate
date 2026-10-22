import { expect, test } from "@playwright/test";
import { keysFor, newWorksheet, signUp } from "./helpers";

const CHAIN = "calc1.derivatives.chain_rule";

test("signed-out visitors are sent to sign in and back", async ({ page }) => {
  await page.goto("/progress");
  await expect(page).toHaveURL(/\/login\?next=%2Fprogress/);
});

test("miss, similar problem, hint ladder, then clear after retry", async ({ page }) => {
  await signUp(page);
  const id = await newWorksheet(page, [CHAIN]);
  await expect(page).toHaveURL(new RegExp(`/practice/${id}\\?problem=1`));

  const answer = page.getByRole("textbox", { name: "Your answer" });
  const check = page.getByRole("button", { name: "Check answer" });

  // Unreadable input is explained and not counted.
  await answer.fill("sin(");
  await check.click();
  await expect(page.getByText("I couldn't read that yet.")).toBeVisible();
  await expect(page.getByText("This doesn't count as a miss.")).toBeVisible();

  // A wrong answer shows what was typed, where to look, and a similar problem button.
  let keys = keysFor(id);
  await answer.fill(keys[0].wrong);
  await check.click();
  await expect(page.getByText("Not quite")).toBeVisible();
  await expect(page.getByText("You answered")).toBeVisible();
  await expect(page.getByText(/Where to look/i)).toBeVisible();
  await expect(page.getByRole("status").or(page.locator("[aria-live=polite]")).first()).toBeAttached();
  await page.getByRole("button", { name: "Try a similar problem" }).click();
  await expect(answer).toBeVisible();
  await expect(answer).toBeFocused();

  // Hints open in order.
  await page.getByRole("button", { name: /Show a hint/ }).click();
  await expect(page.getByText("Nudge")).toBeVisible();
  await page.getByRole("button", { name: /Show bigger hint/ }).click();
  await expect(page.getByText("Bigger hint")).toBeVisible();

  keys = keysFor(id);
  await answer.fill(keys[0].key);
  await check.click();
  await expect(page.getByText("Correct", { exact: true })).toBeVisible();
  await expect(page.getByText("Cleared after retry").first()).toBeVisible();
});

test("keyboard only: type and submit with Enter", async ({ page }) => {
  await signUp(page);
  const id = await newWorksheet(page, [CHAIN], 2);
  const keys = keysFor(id);
  const answer = page.getByRole("textbox", { name: "Your answer" });
  await answer.focus();
  await page.keyboard.type(keys[0].key);
  await page.keyboard.press("Enter");
  await expect(page.getByText("Correct", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Next problem/ }).press("Enter");
  await expect(page).toHaveURL(/problem=2/);
});

test("worksheet fits a phone screen without sideways scrolling", async ({ page }) => {
  await signUp(page);
  await newWorksheet(page, [CHAIN]);
  await expect(page.getByRole("textbox", { name: "Your answer" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("touch targets are at least 44px", async ({ page }) => {
  await signUp(page);
  await newWorksheet(page, [CHAIN]);
  await expect(page.getByRole("textbox", { name: "Your answer" })).toBeVisible();
  const small = await page.evaluate(() =>
    [...document.querySelectorAll("main button, main a, nav a")]
      .filter((el) => (el as HTMLElement).offsetParent !== null)
      .map((el) => {
        const r = el.getBoundingClientRect();
        return { text: (el.textContent ?? "").trim().slice(0, 30), w: r.width, h: r.height };
      })
      .filter((r) => r.w < 44 || r.h < 44),
  );
  expect(small).toEqual([]);
});

test("no clickable divs", async ({ page }) => {
  await signUp(page);
  await newWorksheet(page, [CHAIN]);
  await expect(page.getByRole("textbox", { name: "Your answer" })).toBeVisible();
  const clickable = await page.evaluate(
    () => [...document.querySelectorAll("div[onclick], span[onclick], li[onclick]")].length,
  );
  expect(clickable).toBe(0);
});

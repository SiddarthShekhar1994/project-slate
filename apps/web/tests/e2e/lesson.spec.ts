import { expect, test } from "@playwright/test";
import { openChainRuleLesson, signUp } from "./helpers";

test.describe("lesson player", () => {
  test.beforeEach(async ({ page }) => {
    await signUp(page);
    await openChainRuleLesson(page);
    await expect(page.getByRole("heading", { level: 1, name: "The chain rule" })).toBeVisible();
  });

  test("plays, writes on the board, and stops for pause and predict", async ({ page }) => {
    await expect(page).toHaveURL(/step=1/);
    // Jump to the step before the first checkpoint, then play through it.
    await page.getByRole("button", { name: /Step 5: Outer derivative/ }).click();
    await expect(page).toHaveURL(/step=5/);
    await page.getByRole("button", { name: "Play" }).click();
    await expect(page.getByRole("heading", { name: "Pause and predict" })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole("button", { name: "Play" })).toBeDisabled();

    await page.getByRole("button", { name: "Choice A: 3 x squared" }).click();
    await expect(page.getByText("Right.")).toBeVisible();
    await page.getByRole("button", { name: /Continue the lesson/ }).click();
    await expect(page).toHaveURL(/step=6/);
  });

  test("keyboard: arrows change step and c toggles captions, reflected in the URL", async ({ page }) => {
    // Shortcuts are scoped to the player; outside it they do nothing.
    await page.locator("body").press("ArrowRight");
    await expect(page).toHaveURL(/step=1/);
    await page.getByRole("region", { name: /Board for step 1/ }).locator("..").focus();
    await page.keyboard.press("ArrowRight");
    await expect(page).toHaveURL(/step=2/);
    await page.keyboard.press("c");
    await expect(page).toHaveURL(/cc=0/);
    await expect(page.getByRole("button", { name: /Captions off/ })).toHaveAttribute("aria-pressed", "false");
  });

  test("speed changes are kept in the URL and survive a reload", async ({ page }) => {
    await page.getByLabel("Speed").selectOption("1.5");
    await expect(page).toHaveURL(/speed=1.5/);
    await page.reload();
    await expect(page.getByLabel("Speed")).toHaveValue("1.5");
  });

  test("ask about this step answers with math rendered", async ({ page }) => {
    await page.getByLabel("Your question").fill("Why do we call the inside u?");
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    await expect(page.locator("ol[aria-live] .katex").first()).toBeVisible();
  });

  test("with a voice, the audio drives the board through a step", async ({ page }) => {
    const voice = page.getByRole("combobox", { name: /^Voice/ });
    test.skip(!(await voice.isEnabled()), "no TTS provider configured (run the API with TTS_PROVIDER=silent)");
    await expect(page.getByText("Preparing voice…")).toBeHidden({ timeout: 15_000 });
    await page.getByRole("button", { name: "Play" }).click();
    // The player moves through several steps by itself, each on its own audio.
    await expect(page).toHaveURL(/step=2/, { timeout: 20_000 });
    await expect(page.locator("audio")).toHaveAttribute("src", /\/api\/media\/tts\//);
    const first = await page.locator("audio").getAttribute("src");
    await expect(page).toHaveURL(/step=3/, { timeout: 25_000 });
    await expect(page.locator("audio")).not.toHaveAttribute("src", first ?? "");
    expect(await page.locator("audio").evaluate((el: HTMLAudioElement) => el.paused)).toBe(false);
  });

  test("the board fits a phone screen", async ({ page }) => {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});

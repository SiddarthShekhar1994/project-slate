import { expect, test } from "@playwright/test";
import { keysFor, newWorksheet, signUp } from "./helpers";

// Chromium's fake microphone plays a tone; the API's fake transcriber turns
// any recording into a fixed question (STT_PROVIDER=fake).
test.use({
  permissions: ["microphone"],
  launchOptions: {
    executablePath: process.env.PW_CHROMIUM_PATH || undefined,
    args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"],
  },
});

test("a spoken question lands in the box to check before asking", async ({ page }) => {
  await signUp(page);
  const status = await page.evaluate(async () => (await fetch("/api/voice")).json());
  test.skip(!status.available, "no speech provider (run the API with STT_PROVIDER=fake)");

  await page.goto("/lesson");
  await page.getByRole("link", { name: /Start lesson/ }).first().click();
  await expect(page).toHaveURL(/\/lesson\/[0-9a-f-]+/);

  const mic = page.getByRole("button", { name: "Ask by voice" });
  await mic.click();
  await expect(page.getByRole("button", { name: "Stop recording" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText(/^Listening/)).toBeVisible();
  await page.waitForTimeout(700);
  await page.keyboard.press("Escape");

  const box = page.getByLabel("Your question");
  await expect(box).toHaveValue("Why do we multiply by the derivative of the inside?");
  await expect(box).toBeFocused();
  await expect(page.getByText(/Here's what Slate heard/)).toBeVisible();
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.locator("ol[aria-live] li").first()).toContainText("derivative of the inside");
});

test("a photo of the work fills the answer, then grading is symbolic as usual", async ({ page }) => {
  await signUp(page);
  const id = await newWorksheet(page, ["calc1.derivatives.power_rule"], 1);
  const [{ key }] = keysFor(id);
  // Reading handwriting needs Claude; here the reading is stubbed and everything after it is real.
  await page.route("**/api/math/photo", (route) =>
    route.fulfill({
      json: { text: key, latex: null, error: null, confidence: 0.9, method: "claude" },
    }),
  );

  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Photo of your work" }).click();
  await (await chooser).setFiles({ name: "work.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff]) });

  const answer = page.getByRole("textbox", { name: "Your answer" });
  await expect(answer).toHaveValue(key);
  await expect(page.getByText(/Read from your photo/)).toBeVisible();
  await expect(page.getByLabel("How Slate reads your answer").locator(".katex")).toBeVisible();
  await page.getByRole("button", { name: "Check answer" }).click();
  await expect(page.getByText("Correct", { exact: true })).toBeVisible();
});

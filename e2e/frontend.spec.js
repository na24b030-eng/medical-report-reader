import { test, expect } from "@playwright/test";
test("sample demo, source evidence and JSON download work without a key", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Try a sample report" }).click();
  await expect(page.locator(".test-card")).toHaveCount(2);
  await expect(page.locator("#result-badge")).toHaveText("Sample demo");
  await page.locator("summary").click();
  await expect(page.locator("#source-text")).toContainText("Hemoglobin 10.2");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download JSON" }).click();
  expect((await download).suggestedFilename()).toBe("plum-report.json");
});
test("key is optional, cleared, and never persisted in browser storage", async ({
  page,
}) => {
  await page.goto("/");
  await page.locator("#report-text").fill("Hemoglobin 10.2 g/dL");
  await page.getByRole("button", { name: "Simplify my report" }).click();
  await expect(page.locator(".test-card")).toHaveCount(1);
  await expect(page.locator("#result-badge")).toContainText("Standard wording");
  await page.locator("#api-key").fill("synthetic-key-for-ui-test");
  expect(await page.locator("#api-key").getAttribute("type")).toBe("password");
  expect(
    await page.evaluate(() => [localStorage.length, sessionStorage.length]),
  ).toEqual([0, 0]);
  await page.reload();
  await expect(page.locator("#api-key")).toHaveValue("");
  await page.locator("#api-key").fill("synthetic-key-for-ui-test");
  await page.getByRole("button", { name: "Clear API key" }).click();
  await expect(page.locator("#api-key")).toHaveValue("");
});
test("image selection works and unsupported files are rejected", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Upload image" }).click();
  await page.locator("#report-image").setInputFiles("samples/report.png");
  await expect(page.locator("#image-preview")).toBeVisible();
  await page.locator("#report-image").setInputFiles({
    name: "bad.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("invalid"),
  });
  await expect(page.getByRole("alert")).toContainText("PNG, JPEG, or WebP");
  await expect(page.locator("#image-preview")).toBeHidden();
});
test("server guardrail is shown without making a Gemini request", async ({
  page,
}) => {
  await page.goto("/");
  await page.locator("#api-key").fill("synthetic-key-for-guardrail");
  await page
    .locator("#report-text")
    .fill("Hemoglobin 10.2 g/dL (High) Reference: 12-15");
  const response = page.waitForResponse((r) =>
    r.url().includes("/reports/simplify/text"),
  );
  await page.getByRole("button", { name: "Simplify my report" }).click();
  expect((await response).status()).toBe(422);
  await expect(page.getByRole("alert")).toContainText("conflicts");
});
test("mobile layout fits and tab keyboard controls work", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("tab", { name: "Paste text" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "Upload image" })).toBeFocused();
  await expect(page.locator("#image-panel")).toBeVisible();
  await page.getByRole("button", { name: "Try a sample report" }).click();
  await expect(page.locator(".test-card")).toHaveCount(2);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

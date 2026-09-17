import { chromium } from "@playwright/test";
import { mkdir, rename, writeFile } from "node:fs/promises";
import { createApp, DEMO_TEXT } from "../src/app.js";
await mkdir("submission", { recursive: true });
const live = Boolean(process.env.GEMINI_API_KEY);
const server = createApp({ configured: false }).listen(0, "127.0.0.1");
await new Promise((r) => server.once("listening", r));
let browser;
try {
  browser = await chromium.launch({
    headless: true,
    channel: process.platform === "win32" ? "msedge" : undefined,
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    bypassCSP: true,
    recordVideo: { dir: "tmp/recordings", size: { width: 1440, height: 1000 } },
  });
  const page = await context.newPage();
  // Overlay captions describe actual operations; no provider responses are fabricated.
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  const caption = async (text) => {
    await page.evaluate((text) => {
      let el = document.getElementById("recording-caption");
      if (!el) {
        el = document.createElement("div");
        el.id = "recording-caption";
        el.setAttribute(
          "style",
          "position:fixed;bottom:18px;left:50%;transform:translateX(-50%);padding:16px 24px;border-radius:10px;background:#173a2e;color:white;z-index:1000;font:16px Arial;box-shadow:0 4px 20px #0002;max-width:90%;text-align:center",
        );
        document.body.append(el);
      }
      el.textContent = text;
    }, text);
    await page.waitForTimeout(2200);
  };
  // CSP disallows inline styles, so use an injected stylesheet through Playwright for recording captions.
  await page.addStyleTag({
    content:
      "#recording-caption{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);padding:16px 24px;border-radius:10px;background:#173a2e;color:white;z-index:1000;font:16px Arial;max-width:90%;text-align:center}",
  });
  await caption(
    live
      ? "Plum: deterministic report processing, local OCR, and optional Gemini language help"
      : "Plum: local report processing and OCR. Gemini language help is not configured.",
  );
  await page.getByRole("button", { name: "Try a sample report" }).click();
  await page.waitForSelector("#results:not([hidden])");
  await page.locator("#results").scrollIntoViewIfNeeded();
  await caption(
    "The sample runs without an API key. Each result includes its source range and explanation.",
  );
  await page.locator("summary").click();
  await page.locator("#source-text").scrollIntoViewIfNeeded();
  await caption(
    "Source evidence and the combined JSON response are available for inspection.",
  );
  {
    if (live) await page.locator("#api-key").fill(process.env.GEMINI_API_KEY);
    await page.locator("#report-text").fill(DEMO_TEXT);
    await page.getByRole("button", { name: "Simplify my report" }).click();
    await page.waitForSelector("#results:not([hidden])", { timeout: 100000 });
    if (
      live &&
      !(await page.locator("#result-badge").textContent()).includes(
        "Gemini wording",
      )
    )
      throw new Error("Gemini wording was not applied");
    await caption(
      "Text parsed and validated by code. Gemini only selects approved plain-language wording.",
    );
    await page.getByRole("tab", { name: "Upload image" }).click();
    await page.locator("#report-image").setInputFiles("samples/report.png");
    await caption(
      "Upload the same synthetic report as an image to demonstrate OCR.",
    );
    await page.getByRole("button", { name: "Simplify my report" }).click();
    await page.waitForSelector("#results:not([hidden])", { timeout: 110000 });
    if (
      live &&
      !(await page.locator("#result-badge").textContent()).includes(
        "Gemini wording",
      )
    )
      throw new Error("Image results did not receive Gemini wording");
    await caption(
      live
        ? "Image processing: local Tesseract OCR, deterministic validation, and Gemini wording."
        : "Real local OCR and deterministic validation completed without a language model.",
    );
  }
  await page.getByRole("tab", { name: "Paste text" }).click();
  await page
    .locator("#report-text")
    .fill("Hemoglobin 10.2 g/dL (High) Reference: 12-15");
  await page.getByRole("button", { name: "Simplify my report" }).click();
  await page.waitForSelector("#error:not([hidden])");
  await page.locator("#error").scrollIntoViewIfNeeded();
  await caption(
    "The conflicting flag is rejected before any Gemini call, saving the user’s quota.",
  );
  await page.locator("#clear-key").click();
  await caption(
    "Users bring their own key. The application does not save keys or reports.",
  );
  const video = page.video();
  await context.close();
  const path = await video.path();
  const output = `submission/${live ? "live-demo" : "offline-preview"}.webm`;
  await rename(path, output);
  await writeFile(
    "submission/recording-status.json",
    JSON.stringify(
      {
        recorded_at: new Date().toISOString(),
        mode: live ? "live-gemini" : "offline-preview",
        file: output,
        includes_live_text: live,
        includes_live_image: live,
      },
      null,
      2,
    ),
  );
  console.log(`Saved ${output}`);
} finally {
  await browser?.close();
  server.close();
}

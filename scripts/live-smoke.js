import assert from "node:assert/strict";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { createApp } from "../src/app.js";
if (!process.env.GEMINI_API_KEY) {
  console.error(
    "Add GEMINI_API_KEY to the gitignored .env file before running this check.",
  );
  process.exit(1);
}
const server = createApp({ configured: false }).listen(0, "127.0.0.1");
await new Promise((r) => server.once("listening", r));
const base = `http://127.0.0.1:${server.address().port}`;
const headers = { "x-gemini-api-key": process.env.GEMINI_API_KEY };
const results = [];
try {
  for (const [label, file] of [
    ["text", "samples/report.txt"],
    ["ocr-typos", "samples/report-ocr-typos.txt"],
  ]) {
    const response = await fetch(base + "/reports/simplify/text", {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ text: await readFile(file, "utf8") }),
      signal: AbortSignal.timeout(100000),
    });
    const data = await response.json();
    assert.equal(
      response.status,
      200,
      `${label}: ${data.reason || "unexpected response"}`,
    );
    assert.equal(
      data.metadata.language.provider,
      "gemini",
      data.metadata.language.reason || "Gemini wording was not applied",
    );
    assert.equal(data.tests.length, 2);
    assert.equal(data.tests[0].value, 10.2);
    assert.equal(data.tests[1].value, 11200);
    results.push({
      check: label,
      status: "passed",
      mode: data.metadata.mode,
      language: data.metadata.language.provider,
    });
    console.log(`${label}: passed`);
  }
  const body = new FormData();
  body.append(
    "image",
    new Blob([await readFile("samples/report.png")], { type: "image/png" }),
    "report.png",
  );
  const response = await fetch(base + "/reports/simplify/image", {
    method: "POST",
    headers,
    body,
    signal: AbortSignal.timeout(100000),
  });
  const data = await response.json();
  assert.equal(
    response.status,
    200,
    `image: ${data.reason || "unexpected response"}`,
  );
  assert.equal(data.tests.length, 2);
  assert.equal(data.tests[0].value, 10.2);
  assert.equal(data.tests[1].value, 11200);
  results.push({ check: "image", status: "passed", mode: data.metadata.mode });
  console.log("image: passed");
  await mkdir("submission", { recursive: true });
  await writeFile(
    "submission/live-verification.json",
    JSON.stringify(
      {
        verified_at: new Date().toISOString(),
        model: process.env.GEMINI_MODEL || "gemini-2.5-flash",
        results,
      },
      null,
      2,
    ),
  );
} catch (error) {
  console.error("Live verification failed:", error.message);
  process.exitCode = 1;
} finally {
  server.close();
}

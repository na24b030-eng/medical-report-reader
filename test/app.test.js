import test from "node:test";
import assert from "node:assert/strict";
import sharp from "sharp";
import { readFile } from "node:fs/promises";
import { createApp, DEMO_TEXT } from "../src/app.js";
import { parseReport, validateExtraction } from "../src/normalize.js";
import { createGemini } from "../src/gemini.js";
import { languageFacts } from "../src/language.js";
const extracted = {
  tests_raw: DEMO_TEXT.split("\n").slice(1),
  uncertain: false,
};
const plan = (facts) => ({
  explanations: facts.map((f) => ({
    id: f.id,
    definition: f.definitions[0],
    assessment: f.assessments[0],
  })),
});
async function server(t, options = {}) {
  const s = createApp(options).listen(0, "127.0.0.1");
  await new Promise((r) => s.once("listening", r));
  t.after(() => new Promise((r) => s.close(r)));
  return "http://127.0.0.1:" + s.address().port;
}
const post = (base, text = DEMO_TEXT, headers = {}) =>
  fetch(base + "/reports/simplify/text", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify({ text }),
  });

test("demo works without a key with report-sourced ranges", async (t) => {
  const base = await server(t);
  const r = await fetch(base + "/api/demo");
  const d = await r.json();
  assert.equal(r.status, 200);
  assert.equal(d.metadata.mode, "demo");
  assert.equal(d.tests[1].value, 11200);
  assert.deepEqual(d.tests[0].ref_range, { low: 12, high: 15 });
});

test("normalizes typos and does not invent missing ranges", () => {
  const [t] = parseReport("Hemglobin 10.2 g/dL");
  assert.equal(t.name, "Hemoglobin");
  assert.equal(t.status, "unknown");
  assert.equal(t.ref_range, null);
});

test("rejects conflicting flags, unsupported tests, duplicates, ambiguous numbers", () => {
  for (const input of [
    "Hemoglobin 10.2 g/dL (High) Reference: 12-15",
    "Vitamin D 20 ng/mL",
    "WBC 11200 /uL\nWBC 11000 /uL",
    "Hemoglobin 1O.2 g/dL",
    "Hemoglobin <10 g/dL",
    "Hemoglobin 10,2 g/dL",
  ])
    assert.throws(() => parseReport(input));
});

test("source validation rejects added, missing, altered and uncertain tests", () => {
  for (const e of [
    {
      tests_raw: [...extracted.tests_raw, "Platelets 200000 /uL"],
      uncertain: false,
    },
    { tests_raw: [extracted.tests_raw[0]], uncertain: false },
    {
      tests_raw: [
        extracted.tests_raw[0].replace("10.2", "12.2"),
        extracted.tests_raw[1],
      ],
      uncertain: false,
    },
    { ...extracted, uncertain: true },
  ])
    assert.throws(() => validateExtraction(DEMO_TEXT, e));
});

test("core text processing needs no key or language provider", async (t) => {
  const base = await server(t, {
    configured: false,
    createClient: () => {
      throw Error("Must not create a provider");
    },
  });
  const r = await post(base);
  const d = await r.json();
  assert.equal(r.status, 200);
  assert.equal(d.metadata.mode, "text");
  assert.equal(d.metadata.language.status, "not_requested");
  assert.equal(d.tests[0].value, 10.2);
});

test("Gemini sees only approved language choices, not report text or values", async (t) => {
  let facts;
  const base = await server(t, {
    gemini: {
      explain: async (input) => {
        facts = input;
        return plan(input);
      },
    },
  });
  const r = await post(base);
  const d = await r.json();
  assert.equal(d.metadata.language.status, "applied");
  assert.equal(d.tests[0].value, 10.2);
  assert.ok(!JSON.stringify(facts).includes("10.2"));
  assert.ok(!JSON.stringify(facts).includes("11200"));
  assert.ok(!("value" in facts[0]));
});

test("model hallucinations cannot change results and trigger explicit fallback", async (t) => {
  const base = await server(t, {
    gemini: {
      explain: async () => ({
        explanations: [
          {
            id: "test_0",
            definition: "You have anemia.",
            assessment: "Start treatment.",
          },
        ],
      }),
    },
  });
  const d = await (await post(base)).json();
  assert.equal(d.metadata.language.status, "fallback");
  assert.equal(d.tests.length, 2);
  assert.ok(!JSON.stringify(d.explanations).includes("anemia"));
});

test("quota failure preserves deterministic results with a visible fallback reason", async (t) => {
  const base = await server(t, {
    gemini: {
      explain: async () => {
        const e = Error("quota");
        e.status = 429;
        throw e;
      },
    },
  });
  const r = await post(base);
  const d = await r.json();
  assert.equal(r.status, 200);
  assert.equal(d.metadata.language.status, "fallback");
  assert.match(d.metadata.language.reason, /quota/);
  assert.equal(d.tests[1].value, 11200);
});

test("user keys are isolated by request and absent from responses", async (t) => {
  const keys = [];
  const base = await server(t, {
    createClient: ({ apiKey }) => {
      keys.push(apiKey);
      return { explain: async (facts) => plan(facts) };
    },
  });
  for (const key of [
    "first-user-test-key-12345",
    "second-user-test-key-12345",
  ]) {
    const r = await post(base, DEMO_TEXT, { "x-gemini-api-key": key });
    assert.ok(!(await r.text()).includes(key));
  }
  assert.deepEqual(keys, [
    "first-user-test-key-12345",
    "second-user-test-key-12345",
  ]);
});

test("rejects empty text and unexpected credential body field", async (t) => {
  const base = await server(t);
  for (const body of [{ text: "" }, { text: DEMO_TEXT, apiKey: "secret" }]) {
    const r = await fetch(base + "/reports/simplify/text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    assert.equal(r.status, 400);
  }
});

test("image endpoint runs real local OCR without Gemini", async (t) => {
  const base = await server(t, { configured: false });
  const body = new FormData();
  body.append(
    "image",
    new Blob([await readFile("samples/report.png")], { type: "image/png" }),
    "report.png",
  );
  const r = await fetch(base + "/reports/simplify/image", {
    method: "POST",
    body,
  });
  const d = await r.json();
  assert.equal(r.status, 200, JSON.stringify(d));
  assert.equal(d.tests[0].value, 10.2);
  assert.equal(d.tests[1].value, 11200);
  assert.equal(d.metadata.ocr.engine, "tesseract");
  assert.ok(d.metadata.ocr.numeric_words_checked >= 4);
  assert.equal(d.metadata.language.status, "not_requested");
});

test("rejects fake images before OCR", async (t) => {
  let called = false;
  const base = await server(t, {
    ocr: async () => {
      called = true;
    },
  });
  const body = new FormData();
  body.append(
    "image",
    new Blob(["not an image"], { type: "image/png" }),
    "bad.png",
  );
  const r = await fetch(base + "/reports/simplify/image", {
    method: "POST",
    body,
  });
  assert.equal(r.status, 400);
  assert.equal(called, false);
});

test("empty image is rejected rather than hallucinating tests", async (t) => {
  const base = await server(t);
  const png = await sharp({
    create: { width: 200, height: 200, channels: 3, background: "#fff" },
  })
    .png()
    .toBuffer();
  const body = new FormData();
  body.append("image", new Blob([png], { type: "image/png" }), "blank.png");
  const r = await fetch(base + "/reports/simplify/image", {
    method: "POST",
    body,
  });
  assert.equal(r.status, 422);
  assert.equal((await r.json()).status, "unprocessed");
});

test("provider sends a structured NLP request and validates its response", async () => {
  const facts = languageFacts(parseReport(DEMO_TEXT));
  const client = createGemini({
    apiKey: "user-test-key",
    fetchImpl: async (_url, options) => {
      assert.equal(options.headers["x-goog-api-key"], "user-test-key");
      const body = JSON.parse(options.body);
      assert.ok(body.generationConfig.responseJsonSchema);
      assert.ok(!JSON.stringify(body).includes("inlineData"));
      return {
        ok: true,
        json: async () => ({
          candidates: [
            {
              finishReason: "STOP",
              content: { parts: [{ text: JSON.stringify(plan(facts)) }] },
            },
          ],
        }),
      };
    },
  });
  assert.deepEqual(await client.explain(facts), plan(facts));
});

test("provider errors are sanitized and malformed responses rejected", async () => {
  for (const response of [
    { ok: false, status: 403 },
    {
      ok: true,
      json: async () => ({
        candidates: [
          {
            finishReason: "STOP",
            content: { parts: [{ text: '{"bad":true}' }] },
          },
        ],
      }),
    },
  ]) {
    const client = createGemini({
      apiKey: "secret",
      fetchImpl: async () => response,
    });
    await assert.rejects(
      client.explain([]),
      (e) => !e.message.includes("secret"),
    );
  }
});

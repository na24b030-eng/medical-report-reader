import { mkdir, writeFile } from "node:fs/promises";
import { DEMO_TEXT } from "../src/app.js";
import { finish, validateExtraction } from "../src/normalize.js";
await mkdir("docs", { recursive: true });
await mkdir("submission", { recursive: true });
const extraction = {
  tests_raw: DEMO_TEXT.split("\n").slice(1),
  uncertain: false,
};
const example = finish(
  validateExtraction(DEMO_TEXT, extraction),
  "demo",
  DEMO_TEXT,
  extraction,
);
const writeJSON = (path, value) =>
  writeFile(path, JSON.stringify(value, null, 2) + "\n");
await writeJSON("samples/expected-response.json", example);
const errorSchema = {
  type: "object",
  required: ["status", "reason"],
  properties: {
    status: { enum: ["error", "unprocessed"] },
    reason: { type: "string" },
  },
};
const successSchema = {
  type: "object",
  required: ["tests", "summary", "status", "explanations", "metadata"],
  properties: {
    tests: {
      type: "array",
      minItems: 1,
      items: {
        type: "object",
        required: ["name", "value", "unit", "status", "ref_range"],
        properties: {
          name: { type: "string" },
          value: { type: "number" },
          unit: { type: "string" },
          status: { enum: ["low", "high", "normal", "unknown"] },
          ref_range: {
            anyOf: [
              { type: "null" },
              {
                type: "object",
                required: ["low", "high"],
                properties: {
                  low: { type: "number" },
                  high: { type: "number" },
                },
              },
            ],
          },
        },
      },
    },
    summary: { type: "string" },
    status: { const: "ok" },
    explanations: {
      type: "array",
      items: {
        type: "object",
        required: ["name", "text"],
        properties: { name: { type: "string" }, text: { type: "string" } },
      },
    },
    metadata: {
      type: "object",
      required: [
        "mode",
        "source_text",
        "tests_raw",
        "evidence",
        "validation",
        "confidence",
        "confidence_note",
        "note",
      ],
      properties: {
        mode: { enum: ["demo", "text", "image"] },
        source_text: { type: "string" },
        tests_raw: { type: "array", items: { type: "string" } },
        evidence: {
          type: "array",
          items: {
            type: "object",
            required: ["name", "source"],
            properties: {
              name: { type: "string" },
              source: { type: "string" },
            },
          },
        },
        validation: { type: "string" },
        confidence: { type: "null" },
        confidence_note: { type: "string" },
        note: { type: "string" },
      },
    },
  },
};
const responses = {
  200: {
    description: "Validated report",
    content: {
      "application/json": {
        schema: { $ref: "#/components/schemas/Report" },
        example,
      },
    },
  },
};
for (const code of [400, 413, 422, 429, 500])
  responses[code] = {
    description: {
      400: "Invalid input",
      401: "Missing key",
      413: "Body too large",
      422: "Unprocessed report",
      429: "Busy or quota exceeded",
      502: "Provider failure",
      504: "Provider timeout",
      500: "Unexpected server failure",
    }[code],
    content: {
      "application/json": { schema: { $ref: "#/components/schemas/Error" } },
    },
  };
await writeJSON("docs/openapi.json", {
  openapi: "3.1.0",
  info: {
    title: "Plum Report Simplifier",
    version: "1.0.0",
    description:
      "Deterministic text processing and local OCR. Optional per-request Gemini key for constrained wording. Provider failures use explicit template fallback.",
  },
  servers: [{ url: "http://127.0.0.1:3000" }],
  components: {
    securitySchemes: {
      GeminiKey: { type: "apiKey", in: "header", name: "x-gemini-api-key" },
    },
    schemas: { Report: successSchema, Error: errorSchema },
  },
  paths: {
    "/health": {
      get: {
        summary: "Health and optional server-key availability",
        responses: { 200: { description: "Service is running" } },
      },
    },
    "/api/demo": {
      get: {
        summary: "Fixed demo fixture; no API key or provider calls",
        responses: { 200: responses["200"] },
      },
    },
    "/reports/simplify/text": {
      post: {
        summary: "Simplify typed report",
        security: [{}, { GeminiKey: [] }],
        requestBody: {
          required: true,
          content: {
            "application/json": {
              schema: {
                type: "object",
                required: ["text"],
                additionalProperties: false,
                properties: {
                  text: { type: "string", minLength: 1, maxLength: 20000 },
                },
              },
              example: { text: DEMO_TEXT },
            },
          },
        },
        responses,
      },
    },
    "/reports/simplify/image": {
      post: {
        summary:
          "Local OCR and simplify one PNG, JPEG or WebP, up to 5 MB and 20 megapixels",
        security: [{ GeminiKey: [] }],
        requestBody: {
          required: true,
          content: {
            "multipart/form-data": {
              schema: {
                type: "object",
                required: ["image"],
                properties: { image: { type: "string", format: "binary" } },
              },
            },
          },
        },
        responses,
      },
    },
  },
});
function item(
  name,
  path,
  { method = "GET", body, status = 200, auth = false } = {},
) {
  return {
    name,
    request: {
      method,
      header: auth
        ? [{ key: "x-gemini-api-key", value: "{{gemini_api_key}}" }]
        : [],
      url: "{{base_url}}" + path,
      ...(body ? { body } : {}),
      description: auth
        ? "Set gemini_api_key locally in Postman. Never export a populated credential."
        : "No credentials needed.",
    },
    event: [
      {
        listen: "test",
        script: {
          type: "text/javascript",
          exec: [
            `pm.test('Expected HTTP status', () => pm.response.to.have.status(${status}));`,
            "pm.test('JSON response', () => pm.expect(pm.response.json()).to.have.property('status'));",
            ...(status === 200 && path !== "/health"
              ? [
                  "pm.test('Two sample results', () => pm.expect(pm.response.json().tests).to.have.lengthOf(2));",
                ]
              : []),
          ],
        },
      },
    ],
  };
}
const textBody = (text) => ({
  mode: "raw",
  raw: JSON.stringify({ text }, null, 2),
  options: { raw: { language: "json" } },
});
await writeJSON("docs/Plum.postman_collection.json", {
  info: {
    name: "Plum submission API",
    schema:
      "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
  },
  variable: [
    { key: "base_url", value: "http://127.0.0.1:3000" },
    { key: "gemini_api_key", value: "", type: "string" },
  ],
  item: [
    item("Health", "/health"),
    item("Demo without a key", "/api/demo"),
    item("Live text report", "/reports/simplify/text", {
      method: "POST",
      auth: true,
      body: textBody(DEMO_TEXT),
    }),
    item("Live image report", "/reports/simplify/image", {
      method: "POST",
      auth: true,
      body: {
        mode: "formdata",
        formdata: [
          { key: "image", type: "file", src: "../samples/report.png" },
        ],
      },
    }),
    item("Reject conflicting flag", "/reports/simplify/text", {
      method: "POST",
      auth: true,
      status: 422,
      body: textBody("Hemoglobin 10.2 g/dL (High) Reference: 12-15"),
    }),
    item("Core processing without key", "/reports/simplify/text", {
      method: "POST",
      status: 200,
      body: textBody(DEMO_TEXT),
    }),
  ],
});
console.log(
  "Prepared OpenAPI spec, Postman collection, and expected response fixture.",
);

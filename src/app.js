import express from "express";
import multer from "multer";
import sharp from "sharp";
import { z } from "zod";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import { createGemini, ServiceError } from "./gemini.js";
import { finish, parseReport, Unprocessed, catalog } from "./normalize.js";
import { readImage } from "./ocr.js";
import { explain } from "./language.js";
export const DEMO_TEXT =
  "CBC:\nHemoglobin 10.2 g/dL (Low) Reference: 12.0-15.0\nWBC 11,200 /uL (High) Reference: 4000-11000";
export function createApp({
  gemini,
  ocr = readImage,
  createClient = createGemini,
  configured = process.env.ALLOW_SERVER_KEY === "true" &&
    Boolean(process.env.GEMINI_API_KEY),
} = {}) {
  const app = express();
  function client(req) {
    if (gemini) return gemini;
    const key = req.get("x-gemini-api-key");
    if (key && !/^[\x21-\x7E]{20,500}$/.test(key))
      throw new ServiceError("Please enter a valid Gemini API key.", 400);
    if (key) return createClient({ apiKey: key });
    return configured ? createClient() : null;
  }
  app.disable("x-powered-by");
  app.use((req, res, next) => {
    req.id = randomUUID();
    res.set({
      "X-Request-Id": req.id,
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
      "Cache-Control": "no-store",
      "Content-Security-Policy":
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    });
    next();
  });
  app.use(express.json({ limit: "100kb" }));
  app.get("/health", (_req, res) =>
    res.json({
      status: "ok",
      gemini_configured: configured,
      ocr: "tesseract-local",
      core: "deterministic",
    }),
  );
  app.get("/api/capabilities", (_req, res) =>
    res.json({
      tests: catalog.map(({ name, unit, units, aliases }) => ({
        name,
        unit,
        accepted_units: units,
        aliases,
      })),
      image_formats: ["png", "jpeg", "webp"],
      max_image_bytes: 5 * 1024 * 1024,
      gemini_role: "Optional constrained language editing only",
    }),
  );
  app.get("/api/demo", async (_req, res) => {
    const tests = parseReport(DEMO_TEXT);
    res.json(
      await explain(
        finish(tests, "demo", DEMO_TEXT, {
          tests_raw: tests.map((t) => t.evidence),
        }),
        null,
      ),
    );
  });
  let active = 0;
  async function withCapacity(work) {
    if (active >= 3)
      throw new ServiceError("Server is busy. Please try again shortly.", 429);
    active++;
    try {
      return await work();
    } finally {
      active--;
    }
  }
  async function processReport(text, mode, nlp, requestId, ocrMetadata) {
    const started = performance.now(),
      tests = parseReport(text);
    const result = finish(tests, mode, text, {
      tests_raw: tests.map((t) => t.evidence),
    });
    result.metadata.request_id = requestId;
    result.metadata.pipeline = [
      "local_input",
      "deterministic_extraction",
      "unit_normalization",
      "range_validation",
      "grounded_language",
    ];
    if (ocrMetadata) result.metadata.ocr = ocrMetadata;
    await explain(result, nlp);
    result.metadata.duration_ms = Math.round(performance.now() - started);
    return result;
  }
  app.post("/reports/simplify/text", async (req, res) => {
    const { text } = z
      .object({ text: z.string().trim().min(1).max(20000) })
      .strict()
      .parse(req.body);
    const nlp = client(req);
    res.json(
      await withCapacity(() => processReport(text, "text", nlp, req.id)),
    );
  });
  const upload = multer({
    storage: multer.memoryStorage(),
    limits: { fileSize: 5 * 1024 * 1024, files: 1, fields: 0 },
  });
  app.post(
    "/reports/simplify/image",
    upload.single("image"),
    async (req, res) => {
      const nlp = client(req);
      if (!req.file)
        throw new ServiceError(
          "Please upload an image using the image field.",
          400,
        );
      const result = await withCapacity(async () => {
        let buffer;
        try {
          const input = sharp(req.file.buffer, { limitInputPixels: 20000000 });
          const meta = await input.metadata();
          if (!["png", "jpeg", "webp"].includes(meta.format) || meta.pages > 1)
            throw new Error("Unsupported image");
          buffer = await input.rotate().png().toBuffer();
        } catch {
          throw new ServiceError(
            "Use a valid single-frame PNG, JPEG, or WebP under 5 MB and 20 megapixels.",
            400,
          );
        }
        const transcription = await ocr(buffer);
        const { text, ...ocrMetadata } = transcription;
        if (!text || text.length > 20000)
          throw new Unprocessed(
            "The OCR result is empty or too long. Upload a crop of the results table.",
          );
        return processReport(text, "image", nlp, req.id, ocrMetadata);
      });
      result.metadata.note +=
        " OCR can misread characters. Compare the displayed source text with the original image.";
      res.json(result);
    },
  );
  app.use(express.static(fileURLToPath(new URL("../public", import.meta.url))));
  app.use((_req, res) =>
    res.status(404).json({ status: "error", reason: "Endpoint not found." }),
  );
  app.use((err, req, res, _next) => {
    let status = 500,
      reason = "An unexpected server error occurred.",
      kind = "error";
    if (err instanceof Unprocessed) {
      status = 422;
      reason = err.message;
      kind = "unprocessed";
    } else if (err instanceof z.ZodError) {
      status = 400;
      reason =
        "Provide a text string between 1 and 20,000 characters, with no extra fields.";
    } else if (err instanceof multer.MulterError) {
      status = 400;
      reason = "Upload one image under 5 MB using the image field.";
    } else if (err.type === "entity.too.large") {
      status = 413;
      reason = "Request body is too large.";
    } else if (err instanceof SyntaxError) {
      status = 400;
      reason = "Invalid JSON request.";
    } else if (err instanceof ServiceError || err.status === 429) {
      status = err.status;
      reason = err.message;
    }
    res.status(status).json({ status: kind, reason, request_id: req.id });
  });
  return app;
}

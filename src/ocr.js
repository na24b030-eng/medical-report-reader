import { createWorker, PSM } from "tesseract.js";
import english from "@tesseract.js-data/eng";
import sharp from "sharp";
import { Unprocessed } from "./normalize.js";

// One local worker at a time bounds memory. No image or transcript leaves the server.
let busy = false;
export async function readImage(buffer) {
  if (busy) {
    const error = new Error(
      "The OCR worker is busy. Please try again shortly.",
    );
    error.status = 429;
    throw error;
  }
  busy = true;
  let worker, timer;
  try {
    const prepared = await sharp(buffer)
      .rotate()
      .flatten({ background: "#fff" })
      .grayscale()
      .normalize()
      .resize({ width: 1800, height: 2400, fit: "inside" })
      .png()
      .toBuffer();
    worker = await createWorker("eng", 1, {
      langPath: english.langPath,
      gzip: true,
      cacheMethod: "none",
      logger: () => {},
    });
    await worker.setParameters({
      tessedit_pageseg_mode: PSM.AUTO,
      preserve_interword_spaces: "1",
    });
    const result = await Promise.race([
      worker.recognize(prepared, {}, { text: true, blocks: true }),
      new Promise((_, reject) => {
        timer = setTimeout(
          () =>
            reject(
              new Unprocessed(
                "OCR timed out. Crop the report to its results table and try again.",
              ),
            ),
          45000,
        );
      }),
    ]);
    const { text, confidence, blocks } = result.data;
    const words = (blocks || []).flatMap((b) =>
      (b.paragraphs || []).flatMap((p) =>
        (p.lines || []).flatMap((l) => l.words || []),
      ),
    );
    const uncertainNumbers = words.filter(
      (w) => /\d/.test(w.text) && w.confidence < 65,
    );
    if (!text.trim() || confidence < 65 || uncertainNumbers.length)
      throw new Unprocessed(
        "OCR could not read the report confidently. Upload a clearer crop or paste the result text.",
      );
    return {
      text,
      confidence: Math.round(confidence) / 100,
      engine: "tesseract",
      numeric_words_checked: words.filter((w) => /\d/.test(w.text)).length,
    };
  } finally {
    clearTimeout(timer);
    await worker?.terminate();
    busy = false;
  }
}

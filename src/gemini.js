import { z } from "zod";
export class ServiceError extends Error {
  constructor(message, status = 502) {
    super(message);
    this.status = status;
  }
}
const planSchema = z
  .object({
    explanations: z
      .array(
        z
          .object({
            id: z.string(),
            definition: z.string().max(500),
            assessment: z.string().max(500),
          })
          .strict(),
      )
      .min(1)
      .max(50),
  })
  .strict();
export function createGemini({
  apiKey = process.env.GEMINI_API_KEY,
  model = process.env.GEMINI_MODEL || "gemini-2.5-flash",
  fetchImpl = fetch,
} = {}) {
  return {
    async explain(facts) {
      if (!apiKey) throw new ServiceError("No Gemini key supplied.", 401);
      let response;
      try {
        response = await fetchImpl(
          `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "x-goog-api-key": apiKey,
            },
            signal: AbortSignal.timeout(30000),
            body: JSON.stringify({
              systemInstruction: {
                parts: [
                  {
                    text: "You are a plain-language editor. For each supplied test id, select exactly one definition and one assessment from its approved alternatives. Choose the simplest, clearest wording for a patient, avoiding repetitive sentence structures across the report. Copy chosen sentences exactly. Include every id once. You must not add medical facts, diagnoses, advice, tests, numbers, or new sentences. Return only the specified JSON.",
                  },
                ],
              },
              contents: [
                { role: "user", parts: [{ text: JSON.stringify(facts) }] },
              ],
              generationConfig: {
                temperature: 0,
                responseMimeType: "application/json",
                responseJsonSchema: z.toJSONSchema(planSchema),
              },
            }),
          },
        );
      } catch {
        throw new ServiceError("Gemini was unreachable or timed out.", 504);
      }
      if (!response.ok)
        throw new ServiceError(
          response.status === 429
            ? "Gemini quota exceeded."
            : "Gemini rejected the language request.",
          response.status === 429 ? 429 : 502,
        );
      try {
        const body = await response.json(),
          candidate = body.candidates?.[0];
        if (candidate?.finishReason !== "STOP")
          throw new Error("Incomplete response");
        const text = candidate.content.parts
          .filter((p) => p.text && !p.thought)
          .map((p) => p.text)
          .join("");
        return planSchema.parse(JSON.parse(text));
      } catch {
        throw new ServiceError("Gemini returned an invalid language response.");
      }
    },
  };
}

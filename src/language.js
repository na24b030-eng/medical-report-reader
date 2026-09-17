import { catalog } from "./normalize.js";

// Approved alternatives make semantic validation deterministic, not another LLM opinion.
export function languageFacts(tests) {
  return tests.map((t, index) => {
    const entry = catalog.find((c) => c.name === t.name);
    const assessment =
      t.status === "unknown"
        ? [
            "The report does not provide enough information to classify this result.",
            "No range or flag was supplied, so this result is not classified.",
          ]
        : t.ref_range
          ? [
              `This result is ${t.status === "normal" ? "within" : t.status === "low" ? "below" : "above"} the reference range supplied in the report.`,
              `Compared with the report’s reference range, this result is ${t.status === "normal" ? "in range" : t.status}.`,
            ]
          : [
              `The report labels this result as ${t.status}, but does not supply a reference range.`,
              `This result is marked ${t.status} in the report. A reference range was not included.`,
            ];
    return {
      id: `test_${index}`,
      name: t.name,
      status: t.status,
      definitions: [entry.meaning, entry.plain || entry.meaning],
      assessments: assessment,
    };
  });
}
export function applyLanguagePlan(result, facts, plan) {
  if (
    !Array.isArray(plan?.explanations) ||
    plan.explanations.length !== facts.length
  )
    throw new Error("Invalid explanation coverage");
  const seen = new Set();
  const explanations = plan.explanations.map((item) => {
    const fact = facts.find((f) => f.id === item.id);
    if (
      !fact ||
      seen.has(item.id) ||
      !fact.definitions.includes(item.definition) ||
      !fact.assessments.includes(item.assessment)
    )
      throw new Error("Unsupported explanation content");
    seen.add(item.id);
    return { name: fact.name, text: `${item.definition} ${item.assessment}` };
  });
  result.explanations = result.tests.map((t) =>
    explanations.find((e) => e.name === t.name),
  );
  result.metadata.language = {
    provider: "gemini",
    status: "applied",
    scope: "Selection of approved plain-language wording only",
  };
  return result;
}
export async function explain(result, client) {
  if (!client) {
    result.metadata.language = {
      provider: "templates",
      status: "not_requested",
    };
    return result;
  }
  const facts = languageFacts(result.tests);
  try {
    return applyLanguagePlan(result, facts, await client.explain(facts));
  } catch (error) {
    result.metadata.language = {
      provider: "templates",
      status: "fallback",
      reason:
        error.status === 429
          ? "Gemini quota was reached. Verified results are still available."
          : error.status
            ? "Gemini could not provide wording. Verified results are still available."
            : "The generated wording failed validation; approved wording was used.",
    };
    return result;
  }
}

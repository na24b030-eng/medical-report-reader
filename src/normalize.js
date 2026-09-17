import Decimal from "decimal.js";
export class Unprocessed extends Error {}

export const catalog = [
  {
    name: "Hemoglobin",
    aliases: ["hemoglobin", "haemoglobin", "hemglobin", "hgb", "hb"],
    unit: "g/dL",
    units: ["g/dl", "g/l"],
    factors: { "g/l": 0.1 },
    meaning:
      "Hemoglobin is the protein in red blood cells that carries oxygen.",
    plain:
      "Hemoglobin helps your red blood cells carry oxygen around your body.",
  },
  {
    name: "WBC",
    aliases: ["wbc", "white blood cell count", "white blood cells"],
    unit: "/uL",
    units: ["/ul", "cells/ul", "10^9/l", "k/ul"],
    factors: { "10^9/l": 1000, "k/ul": 1000 },
    meaning: "White blood cells are part of your immune system.",
    plain: "White blood cells help your body fight infections.",
  },
  {
    name: "Platelets",
    aliases: ["platelets", "platelet count", "plt"],
    unit: "/uL",
    units: ["/ul", "cells/ul", "10^9/l", "k/ul"],
    factors: { "10^9/l": 1000, "k/ul": 1000 },
    meaning: "Platelets help your blood clot.",
    plain: "Platelets are small blood components that help stop bleeding.",
  },
  {
    name: "Glucose",
    aliases: ["glucose", "blood glucose", "fasting glucose"],
    unit: "mg/dL",
    units: ["mg/dl"],
    meaning: "Glucose measures the sugar in your blood.",
  },
  {
    name: "Creatinine",
    aliases: ["creatinine", "serum creatinine"],
    unit: "mg/dL",
    units: ["mg/dl"],
    meaning: "Creatinine is a waste product filtered by your kidneys.",
  },
  {
    name: "Total cholesterol",
    aliases: ["total cholesterol", "cholesterol"],
    unit: "mg/dL",
    units: ["mg/dl"],
    meaning: "Cholesterol is a fatty substance in your blood.",
  },
  {
    name: "TSH",
    aliases: ["tsh", "thyroid stimulating hormone"],
    unit: "mIU/L",
    units: ["miu/l", "uiu/ml"],
    meaning: "TSH is a hormone that signals your thyroid to work.",
  },
  {
    name: "RBC",
    aliases: ["rbc", "red blood cell count"],
    unit: "million/uL",
    units: ["million/ul"],
    meaning: "Red blood cells carry oxygen around your body.",
  },
];
const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
export const clean = (s) =>
  s
    .replace(/10⁹/g, "10^9")
    .normalize("NFKC")
    .replace(/[µμ]/g, "u")
    .replace(/[–\u2014]/g, "-")
    .replace(/\s+/g, " ")
    .trim();
const number = "(?:\\d{1,3}(?:,\\d{3})+|\\d+)(?:\\.\\d+)?";
const aliases = catalog
  .flatMap((c) => c.aliases)
  .sort((a, b) => b.length - a.length)
  .map(escape)
  .join("|");
const pattern = new RegExp(
  `\\b(${aliases})\\s*[:=]?\\s*(${number})\\s*(million/uL|cells/uL|10\\^9/L|k/uL|g/dL|g/L|mg/dL|mIU/L|uIU/mL|/uL)(?![a-z0-9/])(?:\\s*\\((Low|High|Normal|Hgh)\\))?(?:\\s*(?:reference|ref(?:erence)?[ _-]?range|range)\\s*[:=]?\\s*(${number})\\s*-\\s*(${number}))?(?:\\s*\\((Low|High|Normal|Hgh)\\))?`,
  "gi",
);

export function parseReport(text) {
  const source = clean(text);
  const results = [...source.matchAll(pattern)].map((match) => {
    const [, alias, rawValue, rawUnit, before, low, high, after] = match;
    const entry = catalog.find((c) => c.aliases.includes(alias.toLowerCase()));
    if (!entry.units.includes(rawUnit.toLowerCase()))
      throw new Unprocessed(`Unsupported unit for ${entry.name}.`);
    const factor = entry.factors?.[rawUnit.toLowerCase()] || 1;
    const convert = (raw) => {
      const exact = new Decimal(raw.replaceAll(",", "")).mul(factor);
      const value = exact.toNumber();
      if (!Number.isFinite(value) || !exact.eq(new Decimal(value)))
        throw new Unprocessed("A numeric value exceeds safe JSON precision.");
      return value;
    };
    const value = convert(rawValue);
    const ref_range = low ? { low: convert(low), high: convert(high) } : null;
    if (
      !Number.isFinite(value) ||
      (ref_range && ref_range.low > ref_range.high)
    )
      throw new Unprocessed("Invalid value or reference range.");
    const flag = (after || before || "").toLowerCase().replace("hgh", "high");
    const calculated = ref_range
      ? value < ref_range.low
        ? "low"
        : value > ref_range.high
          ? "high"
          : "normal"
      : null;
    if (before && after && before.toLowerCase() !== after.toLowerCase())
      throw new Unprocessed("Conflicting report flags.");
    if (flag && calculated && flag !== calculated)
      throw new Unprocessed(
        `Reported flag conflicts with reference range for ${entry.name}.`,
      );
    return {
      name: entry.name,
      value,
      unit: entry.unit,
      status: calculated || flag || "unknown",
      ref_range,
      evidence: match[0],
      provenance: {
        raw_name: alias,
        raw_value: rawValue,
        raw_unit: rawUnit,
        multiplier: factor,
        status_basis: calculated
          ? "report_range"
          : flag
            ? "report_flag"
            : "unknown",
      },
    };
  });
  if (!results.length)
    throw new Unprocessed(
      "No supported, readable test results found. Include test names, numeric values, and units.",
    );
  if (new Set(results.map((t) => t.name)).size !== results.length)
    throw new Unprocessed(
      "Repeated tests require review; provide one result per test.",
    );
  // Never silently drop unsupported, qualitative, or unreadable test results.
  let remainder = source;
  for (const t of results) remainder = remainder.replace(t.evidence, "");
  remainder = remainder
    .replace(/\b(?:CBC|complete blood count)\b/gi, "")
    .replace(/[\s,:;|]+/g, "");
  if (remainder)
    throw new Unprocessed(
      "Some report content could not be safely parsed. Use only supported test result lines with numeric values and units.",
    );
  return results;
}

export function validateExtraction(text, extracted) {
  const expected = parseReport(text);
  if (extracted.uncertain)
    throw new Unprocessed(
      "Extraction is uncertain. Please provide clearer text or a sharper image.",
    );
  for (const raw of extracted.tests_raw) {
    if (!clean(text).includes(clean(raw)))
      throw new Unprocessed("Extracted evidence is not present in the input.");
  }
  const actual = parseReport(extracted.tests_raw.join("\n"));
  const key = (t) =>
    JSON.stringify([t.name, t.value, t.unit, t.status, t.ref_range]);
  if (
    actual.length !== expected.length ||
    actual.some((t) => !expected.some((e) => key(t) === key(e)))
  ) {
    throw new Unprocessed(
      "Hallucinated, altered, or missing tests compared with the input.",
    );
  }
  return expected;
}

export function finish(tests, mode, sourceText, extraction) {
  const explanations = tests.map((t) => {
    const meaning = catalog.find((c) => c.name === t.name).meaning;
    const assessment =
      t.status === "unknown"
        ? "No reference range or flag was supplied, so this result cannot be classified."
        : t.ref_range
          ? `This result is ${t.status === "normal" ? "within" : t.status === "low" ? "below" : "above"} the reference range provided in the report.`
          : `The report marks this result as ${t.status}; no reference range was provided.`;
    return { name: t.name, text: `${meaning} ${assessment}` };
  });
  return {
    tests: tests.map(({ evidence, provenance, ...t }) => t),
    summary:
      tests
        .map(
          (t) =>
            `${t.name}: ${t.status === "unknown" ? "not classified" : t.status}`,
        )
        .join("; ") + ".",
    status: "ok",
    explanations,
    metadata: {
      mode,
      source_text: sourceText,
      tests_raw: extraction.tests_raw,
      evidence: tests.map((t) => ({
        name: t.name,
        source: t.evidence,
        ...t.provenance,
      })),
      validation:
        "Values, units, ranges and statuses were parsed and validated by deterministic code.",
      confidence: null,
      confidence_note: "No calibrated clinical confidence score is available.",
      note: "Educational explanation, not a diagnosis. Review results with your clinician.",
    },
  };
}

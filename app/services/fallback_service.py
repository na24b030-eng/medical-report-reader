from typing import List, Dict, Any
from app.models.schemas import NormalizedTest, ExplanationResult

# Friendly phrase mapping for common lab tests in summary sentences
FRIENDLY_SUMMARY_NAMES = {
    "Hemoglobin": "hemoglobin",
    "WBC": "white blood cell count",
    "Platelets": "platelet count",
    "RBC": "red blood cell count",
    "Hematocrit": "hematocrit percentage",
    "MCV": "mean red cell volume",
    "MCH": "mean cell hemoglobin",
    "MCHC": "mean cell hemoglobin concentration",
    "RDW": "red cell distribution width",
    "Neutrophils": "neutrophil count",
    "Lymphocytes": "lymphocyte count",
    "Monocytes": "monocyte count",
    "Eosinophils": "eosinophil count",
    "Basophils": "basophil count",
    "ESR": "erythrocyte sedimentation rate",
    "CRP": "C-reactive protein level",
    "Glucose": "blood sugar level",
    "HbA1c": "glycated hemoglobin (HbA1c) level",
    "Creatinine": "creatinine level",
    "BUN": "blood urea nitrogen (BUN) level",
    "Total Cholesterol": "total cholesterol level",
    "Triglycerides": "triglyceride level",
    "LDL": "LDL (bad) cholesterol level",
    "HDL": "HDL (good) cholesterol level",
    "Sodium": "serum sodium level",
    "Potassium": "serum potassium level",
    "Calcium": "calcium level",
    "Total Protein": "total blood protein level",
    "Albumin": "albumin protein level",
    "Bilirubin": "bilirubin level",
    "ALT": "ALT liver enzyme level",
    "AST": "AST liver enzyme level",
    "ALP": "ALP enzyme level",
    "Ferritin": "ferritin iron storage level",
    "TSH": "thyroid stimulating hormone level",
    "Vitamin D": "vitamin D level",
    "Vitamin B12": "vitamin B12 level",
}

def generate_fallback_explanation(
    tests: List[NormalizedTest],
    catalog: Dict[str, Any]
) -> ExplanationResult:
    """
    Deterministic rule-based explanation engine that runs when Gemini is unavailable,
    times out, or produces invalid output.
    Uses curated clinical templates and ensures strict non-diagnostic plain-language communication.
    """
    abnormal_tests = [t for t in tests if t.status in ("low", "high")]

    if not abnormal_tests:
        return ExplanationResult(
            summary="All reported lab tests are within their standard reference ranges.",
            explanations=["All tested markers are currently within normal baseline levels."]
        )

    # 1. Build individual explanations
    explanations: List[str] = []
    summary_fragments: List[str] = []

    for test in abnormal_tests:
        meta = catalog.get(test.name, {})
        explanation_key = f"explanation_{test.status}"
        curated_explanation = meta.get(explanation_key)

        if curated_explanation:
            explanations.append(curated_explanation)
        else:
            # Safe generic fallback
            explanations.append(
                f"{test.status.capitalize()} {test.name} is outside typical baseline values."
            )

        friendly_name = FRIENDLY_SUMMARY_NAMES.get(test.name, test.name.lower())
        summary_fragments.append(f"{test.status} {friendly_name}")

    # 2. Build combined summary sentence
    if len(summary_fragments) == 1:
        summary_sentence = summary_fragments[0].capitalize() + "."
    elif len(summary_fragments) == 2:
        summary_sentence = f"{summary_fragments[0].capitalize()} and {summary_fragments[1]}."
    else:
        summary_sentence = (
            ", ".join(summary_fragments[:-1]).capitalize()
            + f", and {summary_fragments[-1]}."
        )

    return ExplanationResult(
        summary=summary_sentence,
        explanations=explanations
    )

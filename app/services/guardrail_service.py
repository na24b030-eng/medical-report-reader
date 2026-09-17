import difflib
import re
from typing import List, Dict, Any
from app.models.schemas import NormalizedTest, ExplanationResult

class HallucinationDetectedException(Exception):
    """Raised when one or more normalized tests have no verifiable source evidence in input."""
    def __init__(self, reason: str = "hallucinated tests not present in input"):
        self.reason = reason
        super().__init__(self.reason)


# Semantic clusters of closely related tests where clinical descriptive vocabulary overlaps
RELATED_CLUSTERS = [
    {"hemoglobin", "hematocrit", "rbc", "mcv", "mch", "mchc", "rdw"},
    {"wbc", "neutrophils", "lymphocytes", "monocytes", "eosinophils", "basophils"},
    {"total cholesterol", "ldl", "hdl", "triglycerides"},
    {"glucose", "hba1c"},
    {"bun", "creatinine"},
    {"alt", "ast", "alp", "bilirubin", "total protein", "albumin"},
    {"sodium", "potassium", "chloride", "calcium"},
]

def verify_source_evidence(
    normalized_tests: List[NormalizedTest],
    raw_source_text: str,
    catalog: Dict[str, Any]
) -> List[str]:
    """
    Validates that every test in the normalized test list has verifiable grounding
    in the raw OCR/text input.
    Uses regex word boundaries so short symbols (e.g. 'k', 'na', 'ca') do not falsely match
    inside common words like 'check', 'normal', or 'case'.
    Returns a list of ungrounded/hallucinated test names.
    """
    raw_lower = raw_source_text.lower()
    raw_tokens = raw_lower.split()
    hallucinated: List[str] = []

    for test in normalized_tests:
        test_name = test.name
        meta = catalog.get(test_name, {})
        aliases = [test_name.lower()] + [s.lower() for s in meta.get("synonyms", [])]

        # 1. Word-boundary exact match in raw text
        grounded = False
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias)}\b", raw_lower):
                grounded = True
                break

        # 2. If not exact, check token-level fuzzy match (tolerates OCR typos)
        if not grounded:
            for alias in aliases:
                alias_words = alias.split()
                if len(alias_words) == 1 and len(alias) >= 3:
                    matches = difflib.get_close_matches(alias, raw_tokens, n=1, cutoff=0.70)
                    if matches:
                        grounded = True
                        break
                elif len(alias_words) > 1:
                    matches = difflib.get_close_matches(alias_words[0], raw_tokens, n=1, cutoff=0.75)
                    if matches:
                        grounded = True
                        break

        if not grounded:
            hallucinated.append(test_name)

    return hallucinated


def validate_explanation_text(
    explanation: ExplanationResult,
    allowed_tests: List[str],
    catalog: Dict[str, Any]
) -> bool:
    """
    Checks that Gemini's generated explanation does not invent or reference medical tests
    that were not in the validated input findings.
    Permits shared vocabulary within closely related diagnostic clusters (e.g. 'cholesterol' for LDL).
    """
    text_to_check = (explanation.summary + " " + " ".join(explanation.explanations)).lower()
    allowed_names = set(t.lower() for t in allowed_tests)

    # Gather all cluster members that share clinical context with allowed tests
    extended_allowed = set(allowed_names)
    for cluster in RELATED_CLUSTERS:
        if cluster & allowed_names:
            extended_allowed |= cluster

    # Check all tests in the catalog: if a test is from a completely unrelated domain
    # and is specifically referenced, flag as hallucination
    for cat_name, meta in catalog.items():
        cat_lower = cat_name.lower()
        if cat_lower not in extended_allowed:
            # Check canonical name and distinctive synonyms (>= 3 chars)
            syns = [cat_lower] + [s.lower() for s in meta.get("synonyms", [])]
            for s in syns:
                # Require >= 3 characters to avoid false matches on short abbreviations
                if len(s) >= 3:
                    if re.search(rf"\b{re.escape(s)}\b", text_to_check, flags=re.IGNORECASE):
                        return False

    return True

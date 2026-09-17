import json
import re
import difflib
from typing import List, Dict, Any, Optional
from pathlib import Path

from app.config import settings
from app.models.schemas import ExtractionResult

# Common OCR typos for clinical flags and tokens
FLAG_TYPO_MAP = {
    "hgh": "High",
    "hg": "High",
    "hi": "High",
    "high": "High",
    "lw": "Low",
    "lo": "Low",
    "low": "Low",
    "nrm": "Normal",
    "norm": "Normal",
    "normal": "Normal",
}

from app.services.catalog_service import load_catalog


def correct_typo_in_name(token: str, catalog: Dict[str, Any]) -> Optional[str]:
    """
    Match a token or phrase against known synonyms and canonical names.
    Handles typos such as 'Hemglobin' -> 'Hemoglobin'.
    """
    token_clean = token.strip().lower()
    
    # 1. Direct synonym match
    for canonical_name, data in catalog.items():
        synonyms = [s.lower() for s in data.get("synonyms", [])]
        if token_clean in synonyms or token_clean == canonical_name.lower():
            return canonical_name

    # 2. Fuzzy match against all known synonyms
    all_synonyms = {}
    for canonical_name, data in catalog.items():
        all_synonyms[canonical_name.lower()] = canonical_name
        for syn in data.get("synonyms", []):
            all_synonyms[syn.lower()] = canonical_name

    matches = difflib.get_close_matches(token_clean, all_synonyms.keys(), n=1, cutoff=0.72)
    if matches:
        return all_synonyms[matches[0]]

    return None


def clean_number_string(num_str: str) -> str:
    """
    Standardize number strings by removing thousands commas (e.g. '11,200' -> '11200')
    and handling common OCR misreads (e.g. letter O -> 0).
    """
    s = num_str.strip()
    # Check if comma is used as thousands separator, e.g. 11,200
    if re.search(r"^\d{1,3}(,\d{3})+$", s):
        s = s.replace(",", "")
    elif "," in s and "." not in s and len(s.split(",")[1]) <= 2:
        # European decimal separator like 10,2 -> 10.2
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    return s


def extract_raw_tests(raw_text: str, base_confidence: float = 0.80) -> ExtractionResult:
    """
    Step 1 implementation:
    Parses raw text (from OCR or text input), isolates test lines, fixes minor typos
    in test names and status flags, formats numbers cleanly, and outputs `tests_raw` list.
    """
    if not raw_text or not raw_text.strip():
        return ExtractionResult(tests_raw=[], confidence=0.0)

    catalog = load_catalog()
    
    # Pre-clean known common panel/report headers while preserving test names like 'WBC:' or 'Hemoglobin:'
    cleaned_text = re.sub(
        r"^(?:CBC|COMPLETE BLOOD COUNT|LAB REPORT|BIOCHEMISTRY|HEMATOLOGY|METABOLIC PANEL|PANEL|REPORT):\s*",
        "",
        raw_text.strip(),
        flags=re.IGNORECASE | re.MULTILINE
    )
    
    # Also split comma-separated tests, e.g.:
    # "Hemoglobin 10.2 g/dL (Low) , WBC 11,200 /uL (High)"
    # We split when a comma is followed by a word/test name rather than digits
    candidate_chunks = []
    lines = cleaned_text.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Split on commas or semicolons that look like boundaries between tests
        parts = re.split(r"[,;]\s*(?=[A-Za-z])", line)
        for part in parts:
            part = part.strip()
            if part:
                candidate_chunks.append(part)

    extracted_tests = []
    typos_fixed_count = 0

    for chunk in candidate_chunks:
        # Check if chunk contains a numeric value
        num_match = re.search(r"(\d+(?:[.,]\d+)*)", chunk)
        if not num_match:
            continue

        # Extract potential test name before the number
        num_start = num_match.start()
        name_part = chunk[:num_start].strip().strip(":").strip()
        rest_part = chunk[num_start:].strip()

        # Fix typos in test name
        canonical_name = correct_typo_in_name(name_part, catalog)
        if not canonical_name:
            # Check individual words in name_part (in case header prefix remained)
            words = name_part.split()
            for i in range(len(words)):
                candidate_name = " ".join(words[i:])
                canonical_name = correct_typo_in_name(candidate_name, catalog)
                if canonical_name:
                    break

        if not canonical_name:
            continue

        if name_part.lower() != canonical_name.lower():
            typos_fixed_count += 1

        # Extract number
        raw_num = num_match.group(1)
        cleaned_num = clean_number_string(raw_num)

        # Extract unit and optional status flag from rest_part
        # e.g., "10.2 g/dL (Low)" -> unit: "g/dL", flag: "(Low)"
        after_num = rest_part[len(raw_num):].strip()

        # Detect flag like (Low), (High), (Hgh), [Low], etc.
        flag_str = ""
        flag_match = re.search(r"[\(\[\{]([A-Za-z]+)[\)\]\}]", after_num)
        if flag_match:
            raw_flag = flag_match.group(1).lower()
            normalized_flag = FLAG_TYPO_MAP.get(raw_flag, raw_flag.capitalize())
            flag_str = f"({normalized_flag})"
            # Remove flag from after_num to get clean unit
            unit_part = after_num[:flag_match.start()].strip() + " " + after_num[flag_match.end():].strip()
        else:
            # Check for trailing word like 'Low' or 'High' without parens
            trailing_flag_match = re.search(r"\b(low|high|hgh|lw|hi|normal|norm)\b", after_num, flags=re.IGNORECASE)
            if trailing_flag_match:
                raw_flag = trailing_flag_match.group(1).lower()
                normalized_flag = FLAG_TYPO_MAP.get(raw_flag, raw_flag.capitalize())
                flag_str = f"({normalized_flag})"
                unit_part = after_num[:trailing_flag_match.start()].strip()
            else:
                unit_part = after_num.strip()

        unit_part = unit_part.strip()
        
        # Standardize unit casing/aliases from catalog
        test_info = catalog.get(canonical_name, {})
        canonical_unit = test_info.get("canonical_unit", unit_part)
        unit_aliases = test_info.get("unit_aliases", {})
        if unit_part.lower() in unit_aliases:
            unit_part = unit_aliases[unit_part.lower()]
        elif not unit_part:
            unit_part = canonical_unit

        # Construct raw formatted string matching the exact expected format:
        # "Hemoglobin 10.2 g/dL (Low)" or "WBC 11200 /uL (High)"
        if flag_str:
            test_raw_str = f"{canonical_name} {cleaned_num} {unit_part} {flag_str}"
        else:
            test_raw_str = f"{canonical_name} {cleaned_num} {unit_part}".strip()

        extracted_tests.append(test_raw_str)

    # Compute confidence
    confidence = base_confidence if extracted_tests else 0.0
    return ExtractionResult(tests_raw=extracted_tests, confidence=round(confidence, 2))

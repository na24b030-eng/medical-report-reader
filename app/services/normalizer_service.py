import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from functools import lru_cache
from app.config import settings
from app.models.schemas import RefRange, NormalizedTest, NormalizationResult, ExtractionResult
from app.services.extractor_service import clean_number_string

from app.services.catalog_service import load_catalog


def parse_raw_test_string(raw_item: str, catalog: Dict[str, Any]) -> Optional[NormalizedTest]:
    """
    Parse a single raw test string (e.g. 'Hemoglobin 10.2 g/dL (Low)' or 'WBC 11200 /uL (High)')
    into a structured NormalizedTest object.
    """
    s = raw_item.strip()
    if not s:
        return None

    # 1. Extract numeric value (supporting commas like 11,200)
    num_match = re.search(r"(\d+(?:[.,]\d+)*)", s)
    if not num_match:
        return None

    raw_val_str = clean_number_string(num_match.group(1))
    try:
        val_float = float(raw_val_str)
        # Format as int if whole number, else float
        val_number = int(val_float) if val_float.is_integer() else val_float
    except ValueError:
        return None

    # 2. Extract name (everything before the number)
    name_candidate = s[:num_match.start()].strip().strip(":").strip()
    if not name_candidate:
        return None
    
    # Match to canonical name from catalog
    canonical_name = None
    test_meta = None
    for c_name, meta in catalog.items():
        synonyms = [syn.lower() for syn in meta.get("synonyms", [])]
        if name_candidate.lower() == c_name.lower() or name_candidate.lower() in synonyms:
            canonical_name = c_name
            test_meta = meta
            break

    if not canonical_name:
        # If not matched directly, check if canonical name starts with name candidate
        for c_name, meta in catalog.items():
            if c_name.lower().startswith(name_candidate.lower()):
                canonical_name = c_name
                test_meta = meta
                break

    # 3. Extract unit and status
    after_num = s[num_match.end():].strip()
    
    # Check for explicit status flag in parens
    explicit_status = None
    flag_match = re.search(r"[\(\[\{](low|high|normal)[\)\]\}]", after_num, flags=re.IGNORECASE)
    if flag_match:
        explicit_status = flag_match.group(1).lower()
        unit_str = after_num[:flag_match.start()].strip() + " " + after_num[flag_match.end():].strip()
    else:
        # Check trailing status word
        trailing_status = re.search(r"\b(low|high|normal)\b", after_num, flags=re.IGNORECASE)
        if trailing_status:
            explicit_status = trailing_status.group(1).lower()
            unit_str = after_num[:trailing_status.start()].strip()
        else:
            unit_str = after_num.strip()

    if not canonical_name:
        # If test is not in catalog and has no explicit status flag,
        # we cannot safely evaluate clinical status. Reject to prevent false-normal classification.
        if not explicit_status:
            return None
        canonical_name = name_candidate.title()
        test_meta = {
            "canonical_unit": "",
            "ref_range": {"low": 0.0, "high": 0.0}
        }

    unit_str = unit_str.strip()
    canonical_unit = test_meta.get("canonical_unit", unit_str)
    unit_aliases = test_meta.get("unit_aliases", {})
    if unit_str.lower() in unit_aliases:
        final_unit = unit_aliases[unit_str.lower()]
    elif unit_str:
        final_unit = unit_str
    else:
        final_unit = canonical_unit

    # 4. Reference range
    catalog_range = test_meta.get("ref_range", {"low": 0.0, "high": 0.0})
    ref_low = float(catalog_range.get("low", 0.0))
    ref_high = float(catalog_range.get("high", 0.0))
    ref_range = RefRange(low=ref_low, high=ref_high)

    # Unit multiplier scaling (e.g. WBC in K/uL -> *1000, Platelets in lakhs -> *100000)
    raw_unit_lower = unit_str.lower()
    if any(k in raw_unit_lower for k in ("k/", "10^3", "thousand")) and ref_low >= 1000 and val_float < 100:
        val_float = val_float * 1000
        val_number = int(val_float) if val_float.is_integer() else val_float
    elif any(l in raw_unit_lower for l in ("lakh", "10^5")) and ref_low >= 10000 and val_float < 100:
        val_float = val_float * 100000
        val_number = int(val_float) if val_float.is_integer() else val_float

    # 5. Deterministic status calculation
    # Pure Python logic: compare numeric value to reference range bounds
    if ref_low != 0.0 or ref_high != 0.0:
        if val_float < ref_low:
            calculated_status = "low"
        elif val_float > ref_high:
            calculated_status = "high"
        else:
            calculated_status = "normal"
    elif explicit_status:
        calculated_status = explicit_status
    else:
        return None

    return NormalizedTest(
        name=canonical_name,
        value=val_number,
        unit=final_unit,
        status=calculated_status,
        ref_range=ref_range
    )


def normalize_extracted_tests(extraction: ExtractionResult, base_confidence: float = 0.84) -> NormalizationResult:
    """
    Step 2 implementation:
    Takes ExtractionResult, parses each test, standardizes names, units, ranges, and statuses.
    Output conforms strictly to the NormalizationResult schema.
    """
    catalog = load_catalog()
    normalized_list: List[NormalizedTest] = []

    for raw_test_line in extraction.tests_raw:
        item = parse_raw_test_string(raw_test_line, catalog)
        if item:
            normalized_list.append(item)

    conf = base_confidence if normalized_list else 0.0
    return NormalizationResult(tests=normalized_list, normalization_confidence=round(conf, 2))

"""Pure, deterministic extraction and normalization. No network or model calls."""

import re
from decimal import Decimal, InvalidOperation, localcontext

from app.catalog import BY_ALIAS, CATALOG
from app.schemas import Evidence, NormalizedTest, ReferenceRange, Unprocessed


def _unit_pattern(u: str) -> str:
    parts = u.split("/")
    return r"\s*/\s*".join(re.escape(p) for p in parts)


NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?|\.\d+)"
ALIASES = "|".join(re.escape(a) for a in sorted(BY_ALIAS, key=len, reverse=True))
UNITS = "|".join(
    _unit_pattern(u) for u in sorted({u for t in CATALOG for u in t.factors}, key=len, reverse=True)
)
FLAG = r"low|high|normal|hgh|h|l|n"
PATTERN = re.compile(
    rf"\b(?P<name>{ALIASES})\s*[:=–—\-]?"
    rf"\s*(?P<value>{NUMBER})\s*"
    rf"(?P<unit>{UNITS})(?![a-z0-9/^])"
    rf"(?:\s*(?:\((?P<flag1>{FLAG})\)|(?P<flag2>{FLAG})\b))?"
    rf"(?:\s*(?:(?:ref(?:erence)?\.?(?:[ _-]?range)?|range|norm(?:al)?)\s*[:=]?\s*|\[|\()?"
    rf"(?P<low>{NUMBER})\s*(?:-|to)\s*(?P<high>{NUMBER})\s*[\])]?"
    rf"(?:\s*(?:\((?P<flag3>{FLAG})\)|(?P<flag4>{FLAG})\b))?)?",
    re.IGNORECASE,
)

METADATA_LINE = re.compile(
    r"^\s*(?:"
    r"[-=_~*#]{2,}\s*|"
    r".*?\b(?:healthcare|diagnostics|laboratory|labs?|hospital|clinic|pathology|pathologist)\b.*|"
    r"(?:patient(?:\s*name)?|name|age|gender|sex|date|time|specimen|sample(?:\s*id)?|"
    r"physician|doctor|dr\.?|ordering|referred\s*by|report(?:\s*date)?|final\s*report|end\s*of\s*report|"
    r"verified\s*by|notes?|methodology|automated\s*hematology|"
    r"test\s*name|result|units?|reference(?:\s*interval|\s*range)?|flag|status|"
    r"cbc|complete\s*blood\s*count)\b.*"
    r")$",
    re.IGNORECASE,
)


def normalized_source(text: str) -> str:
    # Character substitutions are explicit; digits are never guessed or repaired.
    return (
        text.replace("µ", "u")
        .replace("μ", "u")
        .replace("–", "-")
        .replace("\u2014", "-")
        .replace("10⁹", "10^9")
        .replace("10¹²", "10^12")
    )


def convert(raw: str, factor: str) -> float:
    try:
        with localcontext() as ctx:
            ctx.prec = max(30, len(raw) + 10)
            exact = Decimal(raw.replace(",", "")) * Decimal(factor)
            value = float(exact)
            if not exact.is_finite() or Decimal(str(value)) != exact:
                raise Unprocessed("Numeric precision would be lost in JSON output.")
            return value
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise Unprocessed("Invalid numeric value.") from exc


def parse(text: str) -> tuple[list[NormalizedTest], list[Evidence], str]:
    source = normalized_source(text)
    matches = list(PATTERN.finditer(source))
    if not matches:
        raise Unprocessed(
            "No supported readable results found. Include test names, numeric values and units."
        )
    remaining = list(source)
    tests, evidence = [], []
    seen = set()
    flags = {"l": "low", "h": "high", "n": "normal", "hgh": "high"}
    for match in matches:
        raw = match.groupdict()
        definition = BY_ALIAS[raw["name"].lower()]
        if definition.name in seen:
            raise Unprocessed(f"Repeated {definition.name} results require manual review.")
        seen.add(definition.name)
        factor = definition.factors.get(re.sub(r"\s+", "", raw["unit"].lower()))
        if factor is None:
            raise Unprocessed(f"Unsupported unit for {definition.name}.")
        value = convert(raw["value"], factor)
        ref = (
            ReferenceRange(low=convert(raw["low"], factor), high=convert(raw["high"], factor))
            if raw["low"]
            else None
        )
        if ref and ref.low > ref.high:
            raise Unprocessed("Reference-range minimum exceeds its maximum.")
        supplied = {
            flags.get(raw[key].lower(), raw[key].lower())
            for key in ("flag1", "flag2", "flag3", "flag4")
            if raw[key]
        }
        if len(supplied) > 1:
            raise Unprocessed("Conflicting flags in the report.")
        flag = next(iter(supplied), None)
        status = (
            ("low" if value < ref.low else "high" if value > ref.high else "normal")
            if ref
            else flag or "unknown"
        )
        if ref and flag and flag != status:
            raise Unprocessed(
                f"Reported flag conflicts with reference range for {definition.name}."
            )
        tests.append(
            NormalizedTest(
                name=definition.name,
                value=value,
                unit=definition.unit,
                status=status,
                ref_range=ref,
            )
        )
        corrections = []
        if raw["name"].lower() == "hemglobin":
            corrections.append("Hemglobin -> Hemoglobin")
        if any((raw[key] or "").lower() == "hgh" for key in ("flag1", "flag2", "flag3", "flag4")):
            corrections.append("Hgh -> High")
        evidence.append(
            Evidence(
                test_id=f"test_{len(tests)}",
                source_text=match.group(),
                source_start=match.start(),
                source_end=match.end(),
                raw_name=raw["name"],
                raw_value=raw["value"],
                raw_unit=raw["unit"],
                conversion_factor=factor,
                status_basis="report_range" if ref else "report_flag" if flag else "unavailable",
                corrections=corrections,
            )
        )
        remaining[match.start() : match.end()] = " " * (match.end() - match.start())
    unparsed_text = "".join(remaining)
    cleaned_lines = [line for line in unparsed_text.splitlines() if not METADATA_LINE.match(line)]
    remainder = re.sub(r"[\s,:;|/.\-()]", "", "".join(cleaned_lines))
    if remainder:
        raise Unprocessed(
            "Unparsed content remains. Use supported result lines; unknown or unreadable results cannot be silently omitted."
        )
    return tests, evidence, source


def verify(tests: list[NormalizedTest], evidence: list[Evidence], source: str) -> None:
    """Independent final comparison protects against downstream additions/changes."""
    expected, expected_evidence, _ = parse(source)
    if tests != expected or evidence != expected_evidence:
        raise Unprocessed(
            "hallucinated tests not present in input or results altered after extraction"
        )
    if any(source[e.source_start : e.source_end] != e.source_text for e in evidence):
        raise Unprocessed("Source evidence does not match the input.")

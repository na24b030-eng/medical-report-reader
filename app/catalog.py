from dataclasses import dataclass


@dataclass(frozen=True)
class TestDefinition:
    name: str
    aliases: tuple[str, ...]
    unit: str
    factors: dict[str, str]
    definitions: tuple[str, str]


CATALOG = (
    TestDefinition(
        "Hemoglobin",
        ("hemoglobin", "haemoglobin", "hemglobin", "hgb", "hb"),
        "g/dL",
        {"g/dl": "1", "g/l": "0.1"},
        (
            "Hemoglobin carries oxygen in your red blood cells.",
            "Hemoglobin helps red blood cells carry oxygen around your body.",
        ),
    ),
    TestDefinition(
        "WBC",
        ("wbc", "white blood cell count", "white blood cells"),
        "/uL",
        {"/ul": "1", "cells/ul": "1", "10^9/l": "1000", "k/ul": "1000"},
        (
            "White blood cells are part of your immune system.",
            "White blood cells help your body fight infections.",
        ),
    ),
    TestDefinition(
        "Platelets",
        ("platelets", "platelet count", "plt"),
        "/uL",
        {"/ul": "1", "cells/ul": "1", "10^9/l": "1000", "k/ul": "1000"},
        ("Platelets help your blood clot.", "Platelets help stop bleeding by forming clots."),
    ),
    TestDefinition(
        "RBC",
        ("rbc", "red blood cell count"),
        "million/uL",
        {"million/ul": "1", "10^12/l": "1"},
        (
            "Red blood cells carry oxygen around your body.",
            "This test counts the red blood cells that transport oxygen.",
        ),
    ),
    TestDefinition(
        "Glucose",
        ("glucose", "blood glucose", "fasting glucose"),
        "mg/dL",
        {"mg/dl": "1"},
        ("Glucose is the sugar measured in your blood.", "This test measures blood sugar."),
    ),
    TestDefinition(
        "Creatinine",
        ("creatinine", "serum creatinine"),
        "mg/dL",
        {"mg/dl": "1"},
        (
            "Creatinine is a waste product filtered by the kidneys.",
            "Your kidneys filter creatinine from your blood.",
        ),
    ),
    TestDefinition(
        "TSH",
        ("tsh", "thyroid stimulating hormone"),
        "mIU/L",
        {"miu/l": "1", "uiu/ml": "1"},
        (
            "TSH signals the thyroid gland to work.",
            "TSH is a hormone that helps control thyroid activity.",
        ),
    ),
    TestDefinition(
        "Total cholesterol",
        ("total cholesterol", "cholesterol"),
        "mg/dL",
        {"mg/dl": "1"},
        (
            "Cholesterol is a fatty substance in your blood.",
            "This test measures the total cholesterol in your blood.",
        ),
    ),
)
BY_NAME = {item.name: item for item in CATALOG}
BY_ALIAS = {alias: item for item in CATALOG for alias in item.aliases}

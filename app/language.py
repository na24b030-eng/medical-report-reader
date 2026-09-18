"""Constrained NLP: the model edits wording, not report data or medical knowledge."""

import httpx
from pydantic import ValidationError

from app.catalog import BY_NAME
from app.schemas import LanguagePlan, NormalizedTest, Unprocessed


class ProviderUnavailable(Exception):
    pass


def facts_for(tests: list[NormalizedTest]) -> list[dict]:
    facts = []
    for index, test in enumerate(tests, 1):
        if test.status == "unknown":
            assessments = [
                "The report has no range or flag, so this result cannot be classified.",
                "There is not enough information in the report to classify this result.",
            ]
        elif test.ref_range:
            position = {"low": "below", "high": "above", "normal": "within"}[test.status]
            assessments = [
                f"This result is {position} the reference range shown in the report.",
                f"Compared with the report's reference range, this result is {test.status}.",
            ]
        else:
            assessments = [
                f"The report marks this result as {test.status}; no reference range is supplied.",
                f"This result is labeled {test.status} in the report, which does not include a reference range.",
            ]
        facts.append(
            {
                "test_id": f"test_{index}",
                "name": test.name,
                "definitions": list(BY_NAME[test.name].definitions),
                "assessments": assessments,
            }
        )
    return facts


def render_plan(plan: LanguagePlan, facts: list[dict]) -> list[str]:
    if len(plan.items) != len(facts) or len({item.test_id for item in plan.items}) != len(facts):
        raise Unprocessed("hallucinated tests not present in input or missing explanation coverage")
    indexed = {item.test_id: item for item in plan.items}
    output = []
    for fact in facts:
        item = indexed.get(fact["test_id"])
        if (
            not item
            or item.definition not in fact["definitions"]
            or item.assessment not in fact["assessments"]
        ):
            raise Unprocessed(
                "Generated explanation contains an unsupported test, claim or status."
            )
        output.append(f"{item.definition} {item.assessment}")
    return output


def default_explanations(facts: list[dict]) -> list[str]:
    return [f"{fact['definitions'][0]} {fact['assessments'][0]}" for fact in facts]


class GeminiLanguage:
    def __init__(self, model: str, transport: httpx.AsyncBaseTransport | None = None):
        self.model = model
        self.transport = transport

    async def explain(self, facts: list[dict], key: str) -> LanguagePlan:
        import json
        from urllib.parse import quote

        # Values, ranges, raw reports and images never appear in this payload.
        payload = {
            "systemInstruction": {
                "parts": [
                    {
                        "text": "You are a patient-language editor. For every test_id, select exactly one definition and one assessment from that test's approved alternatives. Prefer clear, accessible language and vary repeated sentence structures. Copy selected sentences exactly. Include every test_id once. Never invent medical statements, values, diagnoses, treatments or tests. Return the structured plan only."
                    }
                ]
            },
            "contents": [{"role": "user", "parts": [{"text": json.dumps(facts)}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseJsonSchema": LanguagePlan.model_json_schema(),
            },
        }
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(25, connect=5), transport=self.transport
            ) as client:
                response = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{quote(self.model, safe='')}:generateContent",
                    headers={"x-goog-api-key": key},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                "Gemini could not be reached; approved local explanations were used."
            ) from exc
        if response.status_code != 200:
            reason = (
                "Gemini quota was reached"
                if response.status_code == 429
                else "Gemini rejected the language request"
            )
            raise ProviderUnavailable(f"{reason}; approved local explanations were used.")
        try:
            candidate = response.json()["candidates"][0]
            if candidate.get("finishReason") != "STOP":
                raise ValueError("incomplete")
            text = "".join(
                part["text"]
                for part in candidate["content"]["parts"]
                if "text" in part and not part.get("thought")
            )
            return LanguagePlan.model_validate_json(text)
        except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
            raise Unprocessed("Gemini returned invalid structured explanation output.") from exc

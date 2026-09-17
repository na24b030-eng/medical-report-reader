# Architecture and trust boundaries

## What owns the facts

The report engine is the application. Gemini is an optional, replaceable language adapter.

```text
Typed text ---------------------+
                                |
Image -> decode -> local OCR ---+-> deterministic parser
                                    -> unit conversion
                                    -> range / flag validation
                                    -> source provenance
                                    -> immutable normalized results
                                          |
                         approved language facts only
                                          |
                               optional Gemini editor
                                          |
                           exact semantic allowlist check
                                          |
                         wording accepted OR template fallback
                                          |
                               API response and frontend
```

## Independent report engine

`normalize.js` owns alias recognition, numeric parsing, supported unit conversions, reference ranges, status calculation, duplicate detection and rejection of unparsed content. Unknown readings fail closed. There is no prompt that asks a model to guess a numeric result or choose a range. Every accepted result carries the exact recognized source substring, original name/value/unit, conversion multiplier and status basis in metadata.

Ranges must come from the input. If neither range nor flag is present, status is unknown. Range boundaries are inclusive. If a report's flag disagrees with its range, the entire request returns HTTP 422 rather than choosing one silently. Supported conversions are dimensionally equivalent; population-specific reference values are never substituted.

## Dedicated OCR

`ocr.js` runs Tesseract in a local worker. English language data ships as a dependency, so recognition does not call a cloud OCR or LLM service. Sharp validates image content, enforces a pixel limit, removes metadata, rotates, flattens transparency, normalizes contrast and bounds OCR input dimensions. A single active OCR worker bounds memory. Workers are terminated after each job so one user's image/text does not remain in an idle shared worker.

Overall OCR confidence and numeric-token confidence must meet the configured code threshold (65 on Tesseract's scale). These are heuristic rejection rules, not calibrated probabilities of correctness. A high-confidence OCR error can still pass. All source text remains visible for human comparison. This implementation supports English result lines; complex tables, handwriting and multi-page documents are outside the current parser's scope.

## Precisely limited Gemini role

`language.js` creates approved sentence alternatives from validated facts. `gemini.js` sends only test IDs, canonical names, established statuses and the allowed sentences. It does not send images, raw reports, patient identifiers, numeric results, ranges or API keys in prompt content.

Gemini performs constrained language selection: choose the clearest allowed definition and assessment per finding, minimizing repetitive prose. It cannot generate arbitrary medical content. The server checks every chosen sentence against the alternatives for that exact test, checks coverage and rejects duplicate/unknown test IDs. Selection is intentionally a smaller role than free-form summarization. It could be replaced with a deterministic selector without changing the engine.

A malformed response, unsupported sentence, diagnosis, unknown test, network failure or quota exhaustion uses the already prepared template explanation. The numeric results remain unchanged. `metadata.language` explicitly reports `applied`, `not_requested` or `fallback`; provider failure never masquerades as Gemini success.

## Request lifecycle and credentials

Each request receives a random ID for response correlation, but the application does not persist report bodies or keys. A request-specific `x-gemini-api-key` creates a request-specific language client. There is no global user-key variable, browser storage or cookie. HTTPS is required outside localhost. Hosting layers must not log bodies or this header. Shared server-key fallback is disabled unless explicitly configured.

Three processing requests can run concurrently; OCR has an additional single-worker limit. Capacity is released when work finishes, even if the client disconnects, preventing disconnects from bypassing the work limit. Provider calls time out after 30 seconds; OCR recognition times out after 45 seconds. This is a single-instance deployment model, without a database or distributed job queue.

## Verification strategy

- Deterministic unit tests cover original assignment inputs, typos, absent ranges, conversions, numeric ambiguity and conflicting flags.
- Integration tests run real Tesseract on a synthetic report image and a blank image.
- Language tests reject unsupported medical prose and verify that provider failure preserves the independently calculated results.
- Credential tests verify per-request key isolation and absence of keys in returned responses.
- Browser tests exercise text processing without a key, demo JSON, uploads, errors, keyboard navigation, mobile layout and key clearing.
- Live smoke tests require actual Gemini-applied wording and fail if templates are used as a fallback.

## Deliberate limits

This is an assignment-sized, auditable backend, not a clinically validated medical device. It supports a documented test catalog and constrained result-line format. The architecture makes adding aliases, units and OCR/layout support a code-and-test change rather than a prompt change. No diagnostic or treatment decisions are made.

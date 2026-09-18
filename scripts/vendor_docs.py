"""Pin local Swagger UI assets so API documentation works without a CDN at runtime."""

import hashlib
import json
from pathlib import Path

import httpx

VERSION = "5.17.14"
target = Path("app/static/swagger")
target.mkdir(parents=True, exist_ok=True)
checksums = {}
for name in ("swagger-ui-bundle.js", "swagger-ui.css", "favicon-32x32.png", "LICENSE"):
    response = httpx.get(
        f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{VERSION}/{name}",
        timeout=45,
        follow_redirects=True,
    )
    response.raise_for_status()
    (target / name).write_bytes(response.content)
    checksums[name] = hashlib.sha256(response.content).hexdigest()
(target / "manifest.json").write_text(
    json.dumps({"package": "swagger-ui-dist", "version": VERSION, "sha256": checksums}, indent=2)
    + "\n"
)
print("Vendored pinned Swagger UI assets and license.")

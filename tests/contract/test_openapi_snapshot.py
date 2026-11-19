"""The committed openapi.json is the contract with the frontend (AGENTS.md III)."""

import json

from scripts.export_openapi import OPENAPI_PATH, render


def test_committed_contract_matches_the_app() -> None:
    assert OPENAPI_PATH.exists(), "Run `uv run python scripts/export_openapi.py`."
    assert OPENAPI_PATH.read_text() == render(), (
        "openapi.json is stale: run `uv run python scripts/export_openapi.py`, "
        "commit it, and tell the frontend to regenerate its types."
    )


def test_every_route_is_versioned_and_typed() -> None:
    schema = json.loads(render())
    for path, operations in schema["paths"].items():
        assert path.startswith("/v1/"), path
        for method, operation in operations.items():
            success = [code for code in operation["responses"] if code.startswith("2")]
            assert success, (method, path)
            for code in success:
                if code == "204":
                    continue
                content = operation["responses"][code].get("content", {})
                body = content.get("application/json", {}).get("schema", {})
                # A file download (specs/011) is typed as binary instead.
                files = [
                    c.get("schema")
                    for media, c in content.items()
                    if media != "application/json"
                ]
                binary = {"type": "string", "format": "binary"}
                assert (body and body != {}) or binary in files, (
                    f"untyped response: {method} {path}"
                )

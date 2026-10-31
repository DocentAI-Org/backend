"""Writes the committed API contract, or checks it is up to date (constitution III).

uv run python scripts/export_openapi.py          # regenerate openapi.json
uv run python scripts/export_openapi.py --check  # fail if it is stale
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import create_app  # noqa: E402

OPENAPI_PATH = Path(__file__).resolve().parent.parent / "openapi.json"


def render() -> str:
    return json.dumps(create_app().openapi(), indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    current = render()
    if args.check:
        # A Windows checkout with core.autocrlf has CRLF; Git stores LF.
        committed = (
            OPENAPI_PATH.read_bytes().replace(b"\r\n", b"\n")
            if OPENAPI_PATH.exists()
            else None
        )
        if committed != current.encode():
            print(
                "openapi.json is out of date. Run "
                "`uv run python scripts/export_openapi.py` and commit it.",
                file=sys.stderr,
            )
            return 1
        print("openapi.json is up to date.")
        return 0
    # Bytes: the same file on every OS (no locale encoding, no CRLF).
    OPENAPI_PATH.write_bytes(current.encode())
    print(f"Wrote {OPENAPI_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Generate the keyless /demo fixture from real grounding output.

Reads ANTHROPIC_API_KEY from the environment, runs the real grounding logic
(app.grounding.ground_triples, the same code path as POST /ground) against the
committed example input, and writes app/demo_data/demo.json.

The fixture is written ONLY by this script. Do not hand-edit it: regenerate it
by running this script so the served example always reflects real model output.

    .venv/bin/python scripts/generate_demo.py
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys

from app.config import load_settings
from app.grounding import ground_triples

DEMO_DIR = pathlib.Path(__file__).resolve().parent.parent / "app" / "demo_data"


def main() -> int:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("ANTHROPIC_API_KEY is not set in the environment.", file=sys.stderr)
        return 1

    settings = load_settings()
    source_text = (DEMO_DIR / "demo_input.txt").read_text(encoding="utf-8").strip()
    data = (DEMO_DIR / "demo_input.ttl").read_text(encoding="utf-8")

    result, _cost = ground_triples(data, source_text, key, settings)

    payload = {
        "example": {"source_text": source_text, "data": data},
        "grounding": result.model_dump(mode="json"),
        "meta": {
            "model": settings.grounding_model,
            "generated_at": dt.date.today().isoformat(),
            "note": (
                "Precomputed example, served without a key. Send the same input "
                "to POST /ground with your own X-Anthropic-Key to run it live."
            ),
        },
    }

    out = DEMO_DIR / "demo.json"
    out.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    s = result.summary
    print(
        f"wrote {out}\n  {s.checked} triples checked: "
        f"{s.supported} supported, {s.unsupported} unsupported, {s.unclear} unclear"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

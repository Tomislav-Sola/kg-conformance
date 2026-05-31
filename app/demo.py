"""Loader for the keyless /demo example.

Reads the frozen demo fixture that ships inside the package (app/demo_data/
demo.json) and validates it into the wire model. The fixture is produced only
by scripts/generate_demo.py from real grounding output; nothing here calls a
model. importlib.resources is used so the file is found whether the package is
installed (the container) or editable (local dev).
"""

from __future__ import annotations

import json
from importlib.resources import files

from app.models import DemoResponse

_FIXTURE = "demo_data/demo.json"


def load_demo() -> DemoResponse:
    """Return the precomputed demo payload.

    Raises FileNotFoundError if the fixture has not been generated yet.
    """

    resource = files("app").joinpath(_FIXTURE)
    if not resource.is_file():
        raise FileNotFoundError(
            "Demo fixture missing. Generate it with scripts/generate_demo.py."
        )
    return DemoResponse.model_validate(json.loads(resource.read_text(encoding="utf-8")))

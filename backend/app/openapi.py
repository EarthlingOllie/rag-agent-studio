"""Render the OpenAPI document that `make gen-client` turns into the TypeScript client.

Usage: `python -m app.openapi <output-path>`. Rendering needs no settings or services.
"""

import json
import sys
from pathlib import Path

from app.main import create_app


def render_openapi() -> str:
    return json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    Path(sys.argv[1]).write_text(render_openapi())

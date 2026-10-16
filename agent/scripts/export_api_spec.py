"""Write the Brain's OpenAPI spec to shared/api_spec.json for Member 3 (run from agent/)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "shared" / "api_spec.json"


def export(out: Path = DEFAULT_OUT) -> Path:
    from tecc_brain.app import app

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    print(export())

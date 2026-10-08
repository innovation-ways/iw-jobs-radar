"""Export the OpenAPI document to ``backend/openapi.json`` (ADR-037, ``make openapi``)."""

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from jobs_radar.api.app import create_app
from jobs_radar.core.settings import Settings

SNAPSHOT_PATH = Path(__file__).resolve().parents[3] / "openapi.json"


def build_openapi() -> dict[str, Any]:
    """Build the OpenAPI document from a throw-away application (no database is contacted)."""
    settings = Settings(_env_file=None, db_password=SecretStr("openapi-export"))
    return create_app(settings).openapi()


def main() -> int:
    """Write the snapshot with stable key order so diffs stay reviewable."""
    SNAPSHOT_PATH.write_text(json.dumps(build_openapi(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {SNAPSHOT_PATH}")  # CLI output
    return 0


if __name__ == "__main__":
    sys.exit(main())

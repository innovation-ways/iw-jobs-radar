"""The committed OpenAPI document must match the application (ADR-037).

If this fails after an intentional API change, run ``make openapi`` and commit the result so the
change is reviewed deliberately and the frontend client is regenerated.
"""

import json

from jobs_radar.tools.export_openapi import SNAPSHOT_PATH, build_openapi


def test_committed_openapi_matches_the_application() -> None:
    committed = json.loads(SNAPSHOT_PATH.read_text())
    assert committed == build_openapi(), "OpenAPI changed: run `make openapi` and review the diff"


def test_error_envelope_and_health_are_documented() -> None:
    paths = build_openapi()["paths"]
    assert "/healthz" in paths
    assert "/readyz" in paths

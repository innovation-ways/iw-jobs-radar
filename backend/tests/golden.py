"""Golden files for the characterisation tests of ADR-080.

A golden file records what the system does *today* (synthetic data only). A test compares fresh output
with it; any difference fails. To change a golden file on purpose, run the test with
``UPDATE_GOLDEN=1`` and review the diff like any other code change.
"""

import json
import os
from pathlib import Path
from typing import Any

GOLDEN_DIR = Path(__file__).parent / "golden"


def load_golden(name: str) -> Any:
    """Return the parsed content of ``tests/golden/<name>.json``."""
    return json.loads((GOLDEN_DIR / f"{name}.json").read_text(encoding="utf-8"))


def check_golden(name: str, actual: Any) -> None:
    """Assert that ``actual`` equals the golden file, or rewrite the file when ``UPDATE_GOLDEN=1``."""
    path = GOLDEN_DIR / f"{name}.json"
    # A round trip through JSON gives the exact shape that is stored (tuples become lists, ...).
    fresh = json.loads(json.dumps(actual, ensure_ascii=False, sort_keys=True))
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN_DIR.mkdir(exist_ok=True)
        path.write_text(
            json.dumps(fresh, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return
    assert path.exists(), f"missing golden file {path.name}; run with UPDATE_GOLDEN=1 to create it"
    assert fresh == json.loads(path.read_text(encoding="utf-8")), (
        f"{path.name} differs from the current output; if the change is intended, "
        "run with UPDATE_GOLDEN=1 and review the diff"
    )


def golden_taxonomy() -> dict[str, list[str]]:
    """The term keys of an installation today, by kind, in creation order (from the golden record).

    This is the vocabulary that tests use instead of the frozen seed constants, which only the
    migrations may import (ADR-080, phase 2).
    """
    grouped: dict[str, list[str]] = {}
    for _id, kind, key, *_rest in load_golden("taxonomy_after_migrations")["terms"]:
        grouped.setdefault(kind, []).append(key)
    return grouped


def golden_optional_terms() -> dict[str, frozenset[str]]:
    """The terms introduced after taxonomy version 1 (optional in an older intent, ADR-073)."""
    optional: dict[str, set[str]] = {}
    for _id, kind, key, _label, _origin, introduced, _replaced in load_golden(
        "taxonomy_after_migrations"
    )["terms"]:
        if introduced > 1:
            optional.setdefault(kind, set()).add(key)
    return {kind: frozenset(keys) for kind, keys in optional.items()}

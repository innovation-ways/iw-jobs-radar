"""Unit-test fixtures."""

import os
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove any JOBS_RADAR_* variable so unit tests never depend on the developer's shell."""
    for name in [key for key in os.environ if key.startswith("JOBS_RADAR_")]:
        monkeypatch.delenv(name, raising=False)
    yield

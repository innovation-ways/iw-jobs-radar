"""The operations documentation stays complete: every setting and make target is described."""

import re
from pathlib import Path

from jobs_radar.core.settings import Settings

ROOT = Path(__file__).resolve().parents[3]


def test_every_setting_is_in_the_configuration_reference() -> None:
    text = (ROOT / "docs/operations/configuration-reference.md").read_text()
    missing = [
        f"JOBS_RADAR_{name.upper()}"
        for name in Settings.model_fields
        if f"`JOBS_RADAR_{name.upper()}`" not in text
    ]
    assert missing == [], f"undocumented settings: {missing}"


def test_the_runbooks_mention_the_commands_they_depend_on() -> None:
    runbook = (ROOT / "docs/operations/backup-restore-runbook.md").read_text()
    for command in ("make backup", "make restore-drill", "make restore", "credential_key.txt"):
        assert command in runbook
    makefile = (ROOT / "Makefile").read_text()
    for target in re.findall(r"`make ([a-z-]+)", runbook):
        assert re.search(rf"^{re.escape(target)}:", makefile, re.M), f"make {target} does not exist"

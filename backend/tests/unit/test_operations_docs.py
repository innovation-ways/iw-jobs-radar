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


def test_the_runbook_describes_every_job_board_and_its_failure_reasons() -> None:
    from jobs_radar.adapters.sources.catalogue import CATALOGUE

    runbook = (ROOT / "docs/operations/sources-and-providers-runbook.md").read_text()
    for entry in CATALOGUE:
        assert entry.display_name in runbook, f"{entry.display_name} is not in the runbook"
    for reason in ("authentication", "too_soon", "Profile & intent", "partial"):
        assert reason in runbook, f"the runbook does not explain {reason!r}"


def test_the_limitations_mention_the_job_board_caveats() -> None:
    text = (ROOT / "docs/operations/known-limitations.md").read_text()
    assert "job board" in text.lower()
    assert "ITJobs.pt" in text


def test_the_runbook_describes_every_company_board_type() -> None:
    from jobs_radar.domain.enums import SourceCategory, SourceType
    from jobs_radar.domain.sources import source_category

    runbook = (ROOT / "docs/operations/sources-and-providers-runbook.md").read_text().lower()
    for source_type in SourceType:
        if source_category(source_type) is SourceCategory.COMPANY_BOARD:
            assert source_type.value in runbook, f"{source_type.value} is not in the runbook"

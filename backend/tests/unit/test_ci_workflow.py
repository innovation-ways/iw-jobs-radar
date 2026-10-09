"""The CI workflow is valid, minimal and never uses secrets or the network-only scans (T8)."""

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "ci.yml"


def test_the_workflow_runs_make_check_with_read_only_permissions() -> None:
    data = yaml.safe_load(WORKFLOW.read_text())
    assert data["permissions"] == {"contents": "read"}
    steps = [step.get("run", "") for step in data["jobs"]["check"]["steps"]]
    assert "make check" in steps and "make install" in steps


def test_the_workflow_uses_no_secrets_and_none_of_the_opt_in_or_network_targets() -> None:
    text = WORKFLOW.read_text()
    assert "secrets." not in text
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    for forbidden in (
        "make smoke",
        "make check-all",
        "make test-e2e",
        "security-sast",
        "secret-scan",
    ):
        assert forbidden not in code


def test_the_workflow_pins_pnpm_to_the_version_the_frontend_declares() -> None:
    text = WORKFLOW.read_text()
    assert "corepack prepare" in text and "frontend/package.json" in text

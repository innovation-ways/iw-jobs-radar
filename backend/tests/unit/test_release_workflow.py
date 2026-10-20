"""The release workflow publishes multi-arch images with pinned actions (ADR-079)."""

import re
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "release-please.yml"


def test_the_release_workflow_publishes_multi_arch_images_with_pinned_actions() -> None:
    text = WORKFLOW.read_text()
    data = yaml.safe_load(text)
    assert "linux/amd64,linux/arm64" in text
    assert "release_created" in text
    # Every third-party action is pinned by commit SHA.
    uses = re.findall(r"uses:\s*(\S+)", text)
    assert uses
    for ref in uses:
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", ref), ref
    image_job = data["jobs"]["images"]
    assert image_job["permissions"]["packages"] == "write"
    assert image_job["needs"] == "release-please"

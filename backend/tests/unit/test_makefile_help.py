"""``make help`` must list every target, grouped and coloured, and never fall out of date."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MAKEFILE = (ROOT / "Makefile").read_text()
ESC = "\x1b["

# Targets a person is expected to find (the ones mentioned in CLAUDE.md and the guide).
EXPECTED = {
    "help", "install", "up", "down", "restart", "status", "health", "logs", "urls",
    "test", "test-unit", "test-integration", "test-file", "test-k", "test-failed", "coverage",
    "coverage-html", "test-frontend", "test-frontend-watch", "fe-coverage", "test-e2e",
    "lint", "format", "format-check", "typecheck", "arch-check", "security", "license-check",
    "docs-check", "quality", "fe-lint", "fe-format", "fe-format-check", "fe-typecheck",
    "fe-license-check", "quality-frontend", "security-sast", "secret-scan",
    "docs-schema", "openapi", "api-client", "check", "check-all", "clean",
}  # fmt: skip


def phony_targets() -> set[str]:
    block = re.search(r"^\.PHONY:(.*?)(?:\n\n|\n[A-Za-z#])", MAKEFILE, re.S | re.M)
    assert block, ".PHONY block not found"
    return set(block.group(1).replace("\\", " ").split())


def documented_targets() -> set[str]:
    return set(re.findall(r"^([a-zA-Z0-9_-]+):[^#\n]*?##", MAKEFILE, re.M))


def run_help(**env: str) -> subprocess.CompletedProcess[str]:
    clean = {k: v for k, v in os.environ.items() if k not in {"NO_COLOR", "FORCE_COLOR"}}
    make = shutil.which("make") or "make"
    return subprocess.run(  # noqa: S603  # fixed local command
        [make, "-s", "help"],
        cwd=ROOT,
        env={**clean, **env},
        capture_output=True,
        text=True,
        check=False,
    )


def test_every_phony_target_is_documented() -> None:
    undocumented = phony_targets() - documented_targets()
    assert not undocumented, f"add a '## description' to: {sorted(undocumented)}"


def test_every_documented_target_is_declared_phony() -> None:
    assert documented_targets() - phony_targets() == set()


def test_the_expected_targets_exist() -> None:
    assert EXPECTED - documented_targets() == set()


def test_help_lists_every_documented_target_with_its_description() -> None:
    result = run_help(NO_COLOR="1")
    assert result.returncode == 0, result.stderr
    for target in documented_targets():
        assert re.search(rf"^\s+make {re.escape(target)}\b", result.stdout, re.M), target
    assert "Run one backend test file" in result.stdout


def test_help_is_grouped_in_sections() -> None:
    out = run_help(NO_COLOR="1").stdout
    for section in (
        "Run the app",
        "Backend tests",
        "Frontend tests",
        "End-to-end",
        "Quality gates",
        "Security",
        "Data & contracts",
        "Housekeeping",
    ):
        assert section in out, section


def test_help_has_no_escape_codes_without_a_terminal_or_with_no_color() -> None:
    assert ESC not in run_help(NO_COLOR="1").stdout
    assert ESC not in run_help().stdout  # not a TTY under pytest


def test_help_is_coloured_when_forced() -> None:
    out = run_help(FORCE_COLOR="1").stdout
    assert ESC in out


@pytest.mark.parametrize("target", ["test-file", "test-k", "logs"])
def test_targets_that_need_a_value_explain_how_to_pass_it(target: str) -> None:
    out = run_help(NO_COLOR="1").stdout
    line = next(line for line in out.splitlines() if re.search(rf"make {target}\b", line))
    assert re.search(r"[A-Z]+=", line), line

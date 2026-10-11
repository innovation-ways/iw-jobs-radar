"""Argument handling of the summary sample tool (ADR-059)."""

import pytest

from jobs_radar.tools.summary_sample import main


@pytest.mark.parametrize("args", [["--ids", "a"], ["--ids", "0"], ["--top", "0"], ["--top", "101"]])
def test_bad_arguments_are_refused_before_anything_runs(
    args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(args) == 2
    assert "error" in capsys.readouterr().err

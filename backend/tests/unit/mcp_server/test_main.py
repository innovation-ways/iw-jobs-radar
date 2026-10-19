"""The entry point fails closed and keeps stdout clean (ADR-078 point 10)."""

from pathlib import Path

import pytest

from jobs_radar.mcp_server import __main__ as entry


class _Recorder:
    def __init__(self) -> None:
        self.built = 0
        self.ran = 0

    def build(self, settings: object, api: object) -> "_Recorder":
        self.built += 1
        return self

    def run(self) -> None:
        self.ran += 1


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    recorder = _Recorder()
    monkeypatch.setattr(entry, "build_server", recorder.build)
    return recorder


@pytest.mark.parametrize(
    "environ", [{}, {"JOBS_RADAR_MCP_ENABLED": "false"}, {"JOBS_RADAR_MCP_ENABLED": "1"}]
)
def test_not_enabled_exits_2_with_one_stderr_line_and_builds_nothing(
    environ: dict[str, str],
    recorder: _Recorder,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    code = entry.main({**environ, "JOBS_RADAR_ENV_FILE": str(tmp_path / "none")})
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err.strip().count("\n") == 0
    assert "JOBS_RADAR_MCP_ENABLED=true" in captured.err
    assert (recorder.built, recorder.ran) == (0, 0)


def test_bad_configuration_exits_2_naming_the_variable(
    recorder: _Recorder, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    environ = {
        "JOBS_RADAR_MCP_ENABLED": "true",
        "JOBS_RADAR_MCP_API_URL": "ftp://nope",
        "JOBS_RADAR_ENV_FILE": str(tmp_path / "none"),
    }
    assert entry.main(environ) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "JOBS_RADAR_MCP_API_URL" in captured.err
    assert recorder.built == 0


def test_enabled_builds_and_runs_the_server(
    recorder: _Recorder, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    environ = {
        "JOBS_RADAR_MCP_ENABLED": "true",
        "JOBS_RADAR_ENV_FILE": str(tmp_path / "none"),
    }
    assert entry.main(environ) == 0
    assert (recorder.built, recorder.ran) == (1, 1)
    assert capsys.readouterr().out == ""

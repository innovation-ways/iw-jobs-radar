"""The import-linter contracts must actually catch violations (ADR-029)."""

import subprocess
import sys
import textwrap
from pathlib import Path


def _run_lint_imports(root: Path, config: str) -> subprocess.CompletedProcess[str]:
    config_path = root / "importlinter.ini"
    config_path.write_text(textwrap.dedent(config))
    executable = Path(sys.executable).parent / "lint-imports"
    return subprocess.run(  # noqa: S603  # fixed local executable, temp config
        [str(executable), "--config", str(config_path)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(root), "PATH": str(executable.parent)},
    )


def _make_package(root: Path, adapter_imports: str) -> None:
    for package in ("jr", "jr/adapters", "jr/repositories"):
        (root / package).mkdir(parents=True, exist_ok=True)
        (root / package / "__init__.py").write_text("")
    (root / "jr/repositories/store.py").write_text("VALUE = 1\n")
    (root / "jr/adapters/source.py").write_text(adapter_imports)


CONFIG = """
    [importlinter]
    root_package = jr

    [importlinter:contract:adapters]
    name = Adapters never touch persistence
    type = forbidden
    source_modules = jr.adapters
    forbidden_modules = jr.repositories
"""


def test_adapter_importing_a_repository_is_rejected(tmp_path: Path) -> None:
    _make_package(tmp_path, "from jr.repositories import store\n")
    result = _run_lint_imports(tmp_path, CONFIG)
    assert result.returncode != 0, result.stdout


def test_clean_adapter_passes(tmp_path: Path) -> None:
    _make_package(tmp_path, "VALUE = 2\n")
    result = _run_lint_imports(tmp_path, CONFIG)
    assert result.returncode == 0, result.stdout + result.stderr

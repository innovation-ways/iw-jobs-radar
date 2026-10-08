"""Gate: no AGPL, SSPL or proprietary runtime dependency (ADR-034, ``make license-check``).

Runtime dependencies are taken from ``uv export --no-dev``. Weak-copyleft licences (LGPL) and
anything unknown are reported for human review without failing the gate; AGPL, SSPL and
proprietary or commercial licences fail it.
"""

import importlib.metadata as metadata
import re
import shutil
import subprocess  # runs the local `uv` executable
import sys
from enum import StrEnum


class LicenseVerdict(StrEnum):
    """Outcome of the licence policy for one package."""

    OK = "ok"
    REVIEW = "review"
    DENIED = "denied"


_DENIED = re.compile(
    r"\bAGPL|Affero|\bSSPL|Server Side Public|proprietary|commercial", re.IGNORECASE
)
_REVIEW = re.compile(r"\bL?GPL|General Public|Lesser|^$|^UNKNOWN$", re.IGNORECASE)


def classify_license(text: str) -> LicenseVerdict:
    """Classify a licence string according to the project policy."""
    value = text.strip()
    if _DENIED.search(value):
        return LicenseVerdict.DENIED
    if _REVIEW.search(value):
        return LicenseVerdict.REVIEW
    return LicenseVerdict.OK


def _license_of(name: str) -> str:
    info = metadata.metadata(name)
    declared = info.get("License-Expression") or info.get("License") or ""
    if declared and len(declared) < 60 and "\n" not in declared:
        return declared
    classifiers = [c for c in info.get_all("Classifier") or [] if c.startswith("License ::")]
    return "; ".join(c.split("::")[-1].strip() for c in classifiers) or declared[:60]


def runtime_packages() -> list[str]:
    """Return the names of the pinned runtime dependencies (excluding development groups)."""
    uv = shutil.which("uv") or "uv"
    result = subprocess.run(  # noqa: S603  # fixed command, no user input
        [uv, "export", "--no-dev", "--no-hashes", "--no-emit-project", "--quiet"],
        capture_output=True,
        text=True,
        check=True,
    )
    names = []
    for line in result.stdout.splitlines():
        if line and not line.startswith(("#", " ")):
            names.append(re.split(r"[=;\s]", line, maxsplit=1)[0])
    return sorted(set(names))


def main() -> int:
    """Print review items and fail on denied licences."""
    denied = 0
    for name in runtime_packages():
        try:
            text = _license_of(name)
        except metadata.PackageNotFoundError:
            print(f"not installed: {name}")  # CLI output
            continue
        verdict = classify_license(text)
        if verdict is not LicenseVerdict.OK:
            print(f"{verdict.value}: {name} ({text})")  # CLI output
        denied += verdict is LicenseVerdict.DENIED
    return 1 if denied else 0


if __name__ == "__main__":
    sys.exit(main())

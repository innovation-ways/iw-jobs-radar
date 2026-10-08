"""Gate: every table and every column must carry a comment (CLAUDE.md, ``make docs-check``)."""

import sys

from sqlalchemy import MetaData


def undocumented_columns(metadata: MetaData) -> list[str]:
    """Return ``table.column`` (or ``table (table)``) for each missing comment."""
    violations: list[str] = []
    for table in metadata.sorted_tables:
        if not table.comment:
            violations.append(f"{table.name} (table)")
        violations.extend(
            f"{table.name}.{column.name}" for column in table.columns if not column.comment
        )
    return violations


def main() -> int:
    """Check the application metadata; exit status 1 if anything is undocumented."""
    import jobs_radar.db.models  # noqa: F401  # registers every table on Base.metadata
    from jobs_radar.db.base import Base

    violations = undocumented_columns(Base.metadata)
    for item in violations:
        print(f"undocumented: {item}")  # CLI output
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())

"""The generated database documentation must exist, describe every column and stay up to date."""

from sqlalchemy import BigInteger, Column, MetaData, String, Table

from jobs_radar.tools.generate_schema_docs import (
    SNAPSHOT_PATH,
    build_schema_docs,
    render_schema_markdown,
)


def test_rendering_lists_tables_columns_types_and_comments() -> None:
    metadata = MetaData()
    Table(
        "thing",
        metadata,
        Column("thing_id", BigInteger, primary_key=True, comment="Primary key."),
        Column("name", String(40), nullable=False, comment="Display name."),
        Column("note", String, nullable=True, comment="Optional note."),
        comment="A thing.",
    )
    text = render_schema_markdown(metadata)
    assert "## thing" in text
    assert "A thing." in text
    assert "| `thing_id` | BIGINT | no | Primary key. |" in text
    assert "| `name` | VARCHAR(40) | no | Display name. |" in text
    assert "| `note` | VARCHAR | yes | Optional note. |" in text


def test_the_committed_documentation_matches_the_models() -> None:
    assert SNAPSHOT_PATH.read_text() == build_schema_docs(), (
        "Schema changed: run `make docs-schema`"
    )


def test_every_application_table_is_documented() -> None:
    text = SNAPSHOT_PATH.read_text()
    for table in (
        "owner",
        "career_profile",
        "job_snapshot",
        "match_evaluation",
        "job_inbox_item",
        "worker_heartbeat",
    ):
        assert f"## {table}\n" in text

"""Tests for the quality-gate tools: column documentation and licence policy."""

import pytest
from sqlalchemy import BigInteger, Column, MetaData, String, Table

from jobs_radar.tools.check_column_docs import undocumented_columns
from jobs_radar.tools.check_licenses import LicenseVerdict, classify_license


def _table(metadata: MetaData, comment_on_name: bool, table_comment: str | None) -> None:
    Table(
        "thing",
        metadata,
        Column("thing_id", BigInteger, primary_key=True, comment="Primary key."),
        Column("name", String, comment="Display name." if comment_on_name else None),
        comment=table_comment,
    )


def test_documented_table_has_no_violations() -> None:
    metadata = MetaData()
    _table(metadata, comment_on_name=True, table_comment="A thing.")
    assert undocumented_columns(metadata) == []


def test_missing_column_comment_is_reported() -> None:
    metadata = MetaData()
    _table(metadata, comment_on_name=False, table_comment="A thing.")
    assert undocumented_columns(metadata) == ["thing.name"]


def test_missing_table_comment_is_reported() -> None:
    metadata = MetaData()
    _table(metadata, comment_on_name=True, table_comment=None)
    assert undocumented_columns(metadata) == ["thing (table)"]


@pytest.mark.parametrize(
    ("text", "verdict"),
    [
        ("MIT", LicenseVerdict.OK),
        ("BSD License", LicenseVerdict.OK),
        ("Apache-2.0", LicenseVerdict.OK),
        ("MPL-2.0", LicenseVerdict.OK),
        ("LGPL-3.0-only", LicenseVerdict.REVIEW),
        ("GNU Lesser General Public License v3 (LGPLv3)", LicenseVerdict.REVIEW),
        ("GPL-3.0-or-later", LicenseVerdict.REVIEW),
        ("AGPL-3.0-or-later", LicenseVerdict.DENIED),
        ("GNU Affero General Public License v3", LicenseVerdict.DENIED),
        ("Proprietary", LicenseVerdict.DENIED),
        ("Commercial", LicenseVerdict.DENIED),
        ("SSPL-1.0", LicenseVerdict.DENIED),
        ("", LicenseVerdict.REVIEW),
        ("UNKNOWN", LicenseVerdict.REVIEW),
    ],
)
def test_licence_policy(text: str, verdict: LicenseVerdict) -> None:
    assert classify_license(text) is verdict

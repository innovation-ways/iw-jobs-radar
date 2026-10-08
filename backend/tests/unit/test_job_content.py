"""Content hashing and material-change detection (LLD section 5)."""

from hypothesis import given
from hypothesis import strategies as st

from jobs_radar.domain.job_content import (
    canonical_url,
    changed_fields,
    content_hash,
    material_fields,
    normalise_text,
)

BASE = {
    "title": "Senior AI Solutions Engineer",
    "description_text": "Design and evaluate LLM-powered features.\n\nFully remote within EU.",
    "locations": ["Remote - EU", "Lisbon, Portugal"],
    "apply_url": "https://jobs.example.test/4461450008",
}


def fields(**changes: object) -> dict[str, object]:
    return material_fields(**{**BASE, **changes})  # type: ignore[arg-type]


# --- canonical URLs ----------------------------------------------------------------------------


def test_tracking_parameters_are_removed_and_others_kept() -> None:
    url = "https://Jobs.Example.test/123?utm_source=x&gh_src=abc&lever-source=y&role=eng&utm_campaign=z"
    assert canonical_url(url) == "https://jobs.example.test/123?role=eng"


def test_fragments_and_trailing_noise_are_ignored() -> None:
    assert canonical_url("https://jobs.example.test/123#apply") == "https://jobs.example.test/123"


def test_parameter_order_does_not_matter() -> None:
    assert canonical_url("https://a.test/x?b=2&a=1") == canonical_url("https://a.test/x?a=1&b=2")


def test_a_malformed_url_is_returned_unchanged_not_raised() -> None:
    assert canonical_url("not a url") == "not a url"


# --- text normalisation -------------------------------------------------------------------------


def test_whitespace_runs_collapse() -> None:
    assert normalise_text("  Senior \t Engineer\n ") == "Senior Engineer"


@given(st.text())
def test_normalise_text_is_idempotent(value: str) -> None:
    assert normalise_text(normalise_text(value)) == normalise_text(value)


# --- hashing ------------------------------------------------------------------------------------


def test_the_hash_has_a_stable_prefix_and_length() -> None:
    value = content_hash(fields())
    assert value.startswith("sha256:")
    assert len(value) == len("sha256:") + 64


def test_identical_material_gives_identical_hashes() -> None:
    assert content_hash(fields()) == content_hash(fields())


def test_cosmetic_differences_do_not_change_the_hash() -> None:
    reference = content_hash(fields())
    # extra whitespace, a different paragraph layout, reordered locations, tracking parameters
    cosmetic = fields(
        title="  Senior  AI Solutions   Engineer ",
        description_text="Design and evaluate   LLM-powered features.\nFully remote\nwithin EU.",
        locations=["Lisbon, Portugal", "Remote - EU", "Remote - EU"],
        apply_url="https://jobs.example.test/4461450008?utm_source=newsletter&gh_src=1",
    )
    assert content_hash(cosmetic) == reference


def test_material_differences_change_the_hash() -> None:
    reference = content_hash(fields())
    assert content_hash(fields(title="Staff AI Solutions Engineer")) != reference
    assert content_hash(fields(description_text="A completely different role.")) != reference
    assert content_hash(fields(locations=["Berlin, Germany"])) != reference
    assert content_hash(fields(apply_url="https://jobs.example.test/other")) != reference


@given(st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=6))
def test_location_order_never_matters(locations: list[str]) -> None:
    assert content_hash(fields(locations=locations)) == content_hash(
        fields(locations=list(reversed(locations)))
    )


# --- change detection ------------------------------------------------------------------------------


def test_no_change_means_no_fields() -> None:
    assert changed_fields(fields(), fields()) == []


def test_cosmetic_changes_report_nothing() -> None:
    assert changed_fields(fields(), fields(title="Senior  AI Solutions Engineer ")) == []


def test_each_material_field_is_reported_by_name() -> None:
    assert changed_fields(fields(), fields(title="Other")) == ["title"]
    assert changed_fields(fields(), fields(description_text="New text")) == ["description"]
    assert changed_fields(fields(), fields(locations=["Madrid"])) == ["locations"]
    assert changed_fields(fields(), fields(apply_url="https://jobs.example.test/new")) == [
        "apply_url"
    ]


def test_several_changes_are_listed_in_a_stable_order() -> None:
    result = changed_fields(
        fields(), fields(apply_url="https://x.test/y", title="Other", locations=[])
    )
    assert result == ["title", "locations", "apply_url"]


@given(st.text(), st.text())
def test_changed_fields_agrees_with_the_hash(old_title: str, new_title: str) -> None:
    old, new = fields(title=old_title), fields(title=new_title)
    assert (changed_fields(old, new) == []) == (content_hash(old) == content_hash(new))

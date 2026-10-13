"""The remote-location evidence names the source's places and the text's regions (ADR-069)."""

from tests.unit.matching.builders import dim, intent, job, run


def evidence(**changes: object) -> dict[str, object]:
    changes = {"work_mode": "remote", "remote_regions": ("EU",), **changes}
    result = run(job(**changes), intent(remote_regions=("PT",)))
    return dict(dim(result, "work_arrangement_location").evidence)


def test_both_sides_are_shown_when_the_source_has_places() -> None:
    found = evidence(
        remote_regions=("US",),
        text_remote_regions=("US", "Europe"),
        source_places=("North America", "Remote"),
    )
    assert found["source_places"] == ["North America", "Remote"]
    assert found["text_regions"] == ["US", "Europe"]
    assert found["job_regions"] == ("US",)


def test_nothing_is_added_when_the_source_has_no_places() -> None:
    found = evidence()
    assert "source_places" not in found
    assert "text_regions" not in found

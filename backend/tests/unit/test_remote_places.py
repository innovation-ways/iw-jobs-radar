"""What a source's own remote places allow (ADR-056): the countries a posting is open from."""

import pytest

from jobs_radar.domain.regions import EUROPE
from jobs_radar.services.remote_places import source_remote_countries


@pytest.mark.parametrize(
    ("places", "countries"),
    [
        (["India (Remote)"], {"IN"}),
        (["Netherlands (Remote)"], {"NL"}),
        (["Remote US", "Remote"], {"US"}),  # the bare "Remote" some adapters add says nothing
        (["United States (Remote)", "USA (Remote)"], {"US"}),
        (["Remote - Germany", "Remote - Spain"], {"DE", "ES"}),
        (["Remote, Europe"], set(EUROPE)),
        (["Remote - USA"], {"US"}),  # ADR-058
        (["Remote - USA", "US - Remote Zone 1 (Job Requisitions Only)"], {"US"}),
        (["North America", "Remote"], {"US", "CA", "MX"}),  # ADR-068: Ashby adds the marker
        (["Canada", "United States", "Remote"], {"CA", "US"}),
        (["United Kingdom", "Remote"], {"GB"}),
        (["Remote", "Germany", "Poland"], {"DE", "PL"}),
        (["US - Remote Zone 1"], {"US"}),  # a zone number is filler
        (["Remote Canada"], {"CA"}),
        (["Home Based - Americas"], None),  # replaced below: the Americas, no Portugal
        (["Remote - EU"], None),  # replaced below by the exact EU set
    ],
)
def test_remote_places_bound_to_countries_give_those_countries(
    places: list[str], countries: set[str] | None
) -> None:
    found = source_remote_countries(places)
    if places == ["Home Based - Americas"]:
        assert found is not None and "US" in found and "BR" in found and "PT" not in found
    elif countries is None:
        assert found is not None and "PT" in found and "US" not in found
    else:
        assert found == frozenset(countries)


@pytest.mark.parametrize(
    "places",
    [
        [],
        ["Remote"],  # remote, but open to whom is not said
        ["Seattle", "Remote"],  # an office is named: the source does not limit remote work
        ["New York", "San Francisco", "Toronto"],  # hubs, not a limit (ADR-056.2)
        ["Remote - Portugal", "Berlin"],  # a named office next to a remote place
        ["Remote, Narnia"],  # a region the table does not know cannot limit anything
        ["Remote, San Francisco, CA"],
        ["Home Based - Worldwide"],  # open to everyone
        ["India (Remote)", "Remote - Anywhere"],  # one place is open to everyone
        ["Lisbon, Portugal"],
    ],
)
def test_anything_else_gives_no_limit(places: list[str]) -> None:
    assert source_remote_countries(places) is None


def test_a_group_that_includes_portugal_does_not_exclude_it() -> None:
    found = source_remote_countries(["Remote - EMEA"])
    assert found is not None and "PT" in found and "US" not in found


def test_a_bare_region_next_to_a_remote_marker_limits_remote_work() -> None:
    found = source_remote_countries(["Europe", "Remote"])
    assert found is not None and "PT" in found and "US" not in found  # ADR-068


@pytest.mark.parametrize(
    "places",
    [
        ["North America"],  # no remote marker: could be a hub, not a limit
        ["Lisbon", "Remote"],  # a city next to the marker
        ["United States", "Austin", "Remote"],  # one office among the countries
        ["Europe", "Narnia", "Remote"],  # an unknown place cannot limit anything
        ["Worldwide", "Remote"],  # open to everyone
    ],
)
def test_bare_places_without_a_clear_limit_give_none(places: list[str]) -> None:
    assert source_remote_countries(places) is None

"""Public-dataset adapters against recorded synthetic responses (T7.2, ADR-025, R-00171)."""

import pytest
import respx

from jobs_radar.adapters.enrichment.base import EnrichmentError, PublicApi
from jobs_radar.adapters.enrichment.github import GitHubAdapter
from jobs_radar.adapters.enrichment.gleif import GleifAdapter
from jobs_radar.adapters.enrichment.wikidata import WikidataAdapter
from jobs_radar.adapters.enrichment.wikipedia import WikipediaAdapter
from jobs_radar.core.http import GuardedHttpClient
from jobs_radar.core.url_guard import UrlGuard

WD = "https://www.wikidata.org/w/api.php"


def api(min_interval: float = 0.0) -> PublicApi:
    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    client = GuardedHttpClient(guard=UrlGuard(resolver=resolve), user_agent="JobsRadar/test")
    return PublicApi(client, min_interval=min_interval, sleep=_no_sleep)


async def _no_sleep(seconds: float) -> None:
    return None


def snak(value: object) -> list[dict[str, object]]:
    return [{"mainsnak": {"datavalue": {"value": value}}}]


SEARCH = {
    "search": [
        {"id": "Q1", "label": "Northwind Labs", "description": "American software company"},
        {"id": "Q2", "label": "northwind", "description": "Python library"},
    ]
}
ENTITIES = {
    "entities": {
        "Q1": {
            "labels": {"en": {"value": "Northwind Labs"}},
            "descriptions": {"en": {"value": "American software company"}},
            "claims": {
                "P31": snak({"id": "Q4830453"}),
                "P856": snak("https://www.northwind.example/"),
                "P452": snak({"id": "Q100"}),
                "P1128": snak({"amount": "+4000"}),
                "P159": snak({"id": "Q200"}),
                "P571": snak({"time": "+2013-00-00T00:00:00Z"}),
                "P2037": snak("northwind-labs"),
            },
            "sitelinks": {"enwiki": {"title": "Northwind Labs"}},
        },
        "Q2": {
            "labels": {"en": {"value": "northwind"}},
            "descriptions": {"en": {"value": "Python library"}},
            "claims": {
                "P31": snak({"id": "Q188860"}),
                "P856": snak("https://northwind.example/lib"),
            },
            "sitelinks": {},
        },
    }
}
LABELS = {
    "entities": {
        "Q100": {"labels": {"en": {"value": "software industry"}}},
        "Q200": {"labels": {"en": {"value": "San Francisco"}}},
    }
}


def stub_wikidata() -> None:
    def handler(request):  # type: ignore[no-untyped-def]
        import httpx

        params = dict(request.url.params)
        if params.get("action") == "wbsearchentities":
            return httpx.Response(200, json=SEARCH)
        ids = params.get("ids", "")
        if ids == "Q100|Q200" or ids == "Q200|Q100":
            return httpx.Response(200, json=LABELS)
        return httpx.Response(200, json=ENTITIES)

    respx.get(WD).mock(side_effect=handler)


@respx.mock
async def test_wikidata_returns_the_company_with_sourced_facts_and_skips_a_library() -> None:
    stub_wikidata()
    found = await WikidataAdapter(api()).find("Northwind Labs")
    assert [c.external_id for c in found] == ["Q1"]  # the Python library is not a company
    company = found[0]
    assert company.website == "https://www.northwind.example/"
    facts = company.facts
    assert facts["homepage"].value == "https://www.northwind.example/"
    assert facts["industry"].value == "software industry"
    assert facts["headquarters"].value == "San Francisco"
    assert facts["employee_count"].value == 4000
    assert facts["founded_year"].value == 2013
    assert all(f.licence == "CC0-1.0" for f in facts.values())
    assert all(f.source_url == "https://www.wikidata.org/wiki/Q1" for f in facts.values())
    assert company.wikipedia_title == "Northwind Labs" and company.github_login == "northwind-labs"


@respx.mock
async def test_wikidata_with_no_results_is_empty() -> None:
    respx.get(WD).respond(200, json={"search": []})
    assert await WikidataAdapter(api()).find("Nothing Like This") == []


@respx.mock
async def test_a_failing_dataset_raises_a_classified_error_without_the_query() -> None:
    respx.get(WD).respond(503)
    with pytest.raises(EnrichmentError) as caught:
        await WikidataAdapter(api()).find("Secret Company Name")
    assert caught.value.error_class == "http_error" and "Secret" not in str(caught.value)
    respx.get(WD).respond(200, text="<html>not json</html>")
    with pytest.raises(EnrichmentError) as bad:
        await WikidataAdapter(api()).find("x")
    assert bad.value.error_class == "invalid_response"


@respx.mock
async def test_wikipedia_summary_comes_with_attribution_data() -> None:
    respx.get("https://en.wikipedia.org/api/rest_v1/page/summary/Northwind_Labs").respond(
        200,
        json={
            "title": "Northwind Labs",
            "extract": "Northwind Labs is an American software company.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Northwind_Labs"}},
        },
    )
    summary = await WikipediaAdapter(api()).summary("Northwind Labs")
    assert summary is not None
    assert summary.text.startswith("Northwind Labs is")
    assert summary.url == "https://en.wikipedia.org/wiki/Northwind_Labs"
    assert summary.licence == "CC-BY-SA-4.0"


@respx.mock
async def test_a_missing_wikipedia_page_is_none() -> None:
    respx.get("https://en.wikipedia.org/api/rest_v1/page/summary/Nothing").respond(404)
    assert await WikipediaAdapter(api()).summary("Nothing") is None


GLEIF = "https://api.gleif.org/api/v1/lei-records"


@respx.mock
async def test_gleif_accepts_only_an_exact_name_match() -> None:
    respx.get(GLEIF).respond(
        200,
        json={
            "data": [
                {
                    "id": "LEI0000000000000001",
                    "attributes": {
                        "entity": {
                            "legalName": {"name": "NORTHWIND LABS, INC."},
                            "legalAddress": {"country": "US"},
                            "status": "ACTIVE",
                        }
                    },
                },
                {
                    "id": "LEI0000000000000002",
                    "attributes": {
                        "entity": {
                            "legalName": {"name": "NORTHWIND APS"},
                            "legalAddress": {"country": "DK"},
                            "status": "ACTIVE",
                        }
                    },
                },
            ]
        },
    )
    found = await GleifAdapter(api()).legal_entity("Northwind Labs")
    assert found is not None
    assert (found.lei, found.country, found.status) == ("LEI0000000000000001", "US", "ACTIVE")
    assert found.licence == "CC0-1.0"


@respx.mock
async def test_gleif_with_two_equal_names_is_not_guessed() -> None:
    entity = {
        "legalName": {"name": "ACME LTD"},
        "legalAddress": {"country": "GB"},
        "status": "ACTIVE",
    }
    respx.get(GLEIF).respond(
        200,
        json={
            "data": [
                {"id": "A", "attributes": {"entity": entity}},
                {"id": "B", "attributes": {"entity": entity}},
            ]
        },
    )
    assert await GleifAdapter(api()).legal_entity("Acme") is None


@respx.mock
async def test_github_organisation_gives_website_and_languages() -> None:
    respx.get("https://api.github.com/orgs/northwind-labs").respond(
        200,
        json={
            "login": "northwind-labs",
            "blog": "https://www.northwind.example",
            "description": "We build",
            "public_repos": 12,
            "html_url": "https://github.com/northwind-labs",
        },
    )
    respx.get("https://api.github.com/orgs/northwind-labs/repos").respond(
        200,
        json=[
            {"language": "Python"},
            {"language": "Python"},
            {"language": "Go"},
            {"language": None},
        ],
    )
    org = await GitHubAdapter(api()).organisation("northwind-labs")
    assert org is not None
    assert org.website == "https://www.northwind.example" and org.public_repos == 12
    assert org.languages == ["Python", "Go"]  # most used first


@respx.mock
async def test_github_unknown_org_is_none_and_the_token_is_sent_only_when_set() -> None:
    respx.get("https://api.github.com/orgs/none").respond(404)
    assert await GitHubAdapter(api()).organisation("none") is None
    route = respx.get("https://api.github.com/orgs/ok").respond(
        200, json={"blog": "", "public_repos": 0}
    )
    respx.get("https://api.github.com/orgs/ok/repos").respond(200, json=[])
    await GitHubAdapter(api(), token="ghp_secret").organisation("ok")
    assert route.calls.last.request.headers["authorization"] == "Bearer ghp_secret"
    await GitHubAdapter(api()).organisation("ok")
    assert "authorization" not in route.calls.last.request.headers


@respx.mock
async def test_github_rate_limit_is_reported() -> None:
    respx.get("https://api.github.com/orgs/slow").respond(
        403, headers={"x-ratelimit-remaining": "0"}
    )
    with pytest.raises(EnrichmentError) as caught:
        await GitHubAdapter(api()).organisation("slow")
    assert caught.value.error_class == "rate_limited"


async def test_requests_to_a_dataset_are_spaced_out() -> None:
    sleeps: list[float] = []

    async def record(seconds: float) -> None:
        sleeps.append(seconds)

    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    client = GuardedHttpClient(guard=UrlGuard(resolver=resolve), user_agent="t")
    limited = PublicApi(
        client, min_interval=1.0, sleep=record, clock=iter([0.0, 0.2, 0.2]).__next__
    )
    with respx.mock:
        respx.get("https://example.test/a").respond(200, json={})
        await limited.get_json("https://example.test/a")
        await limited.get_json("https://example.test/a")
    assert sleeps and 0.7 < sleeps[0] <= 1.0

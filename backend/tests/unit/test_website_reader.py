"""The company website reader: same-domain pages only, robots.txt honoured, bounded (ADR-054)."""

import pytest
import respx

from jobs_radar.adapters.enrichment.website import WebsiteReader, page_text, select_page_links
from jobs_radar.core.http import GuardedHttpClient
from jobs_radar.core.url_guard import UrlGuard

SITE = "https://www.northwind.example/"

HOME = """<html><body><nav>
<a href="/about">About us</a><a href="/careers">Careers</a>
<a href="https://blog.northwind.example/engineering">Engineering blog</a>
<a href="https://evil.example/careers">Careers elsewhere</a>
<a href="/pricing">Pricing</a><a href="/remote-work">How we work remotely</a>
<a href="/private/about-secret">About secret</a>
<a href="mailto:hi@northwind.example">Mail</a>
</nav><p>Northwind builds billing software.</p></body></html>"""


def reader(max_pages: int = 8) -> WebsiteReader:
    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    client = GuardedHttpClient(guard=UrlGuard(resolver=resolve), user_agent="JobsRadar/test")

    async def no_sleep(seconds: float) -> None:
        return None

    return WebsiteReader(client, max_pages=max_pages, min_interval=0.0, sleep=no_sleep)


def test_links_keep_the_same_domain_and_relevant_pages() -> None:
    links = select_page_links(SITE, HOME, limit=8)
    assert "https://www.northwind.example/about" in links
    assert "https://www.northwind.example/careers" in links
    assert "https://blog.northwind.example/engineering" in links
    assert "https://www.northwind.example/remote-work" in links
    assert all("evil.example" not in link for link in links)
    assert all("pricing" not in link and not link.startswith("mailto") for link in links)


def test_links_are_limited_and_unique() -> None:
    page = "".join(f'<a href="/about/{i}">About {i}</a>' for i in range(30)) + HOME
    links = select_page_links(SITE, page, limit=3)
    assert len(links) == 3
    assert len(set(links)) == 3


@pytest.mark.asyncio
async def test_reads_home_and_linked_pages_and_obeys_robots() -> None:
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://www.northwind.example/robots.txt").respond(
            200, text="User-agent: *\nDisallow: /private/\n"
        )
        mock.get(SITE).respond(200, html=HOME)
        mock.get("https://www.northwind.example/about").respond(
            200, html="<p>We were founded in 2015.</p>"
        )
        mock.get("https://www.northwind.example/careers").respond(
            200, html="<p>We hire across Europe.</p>"
        )
        blocked = mock.get("https://www.northwind.example/private/about-secret").respond(200)
        mock.get("https://blog.northwind.example/robots.txt").respond(404)
        mock.get("https://blog.northwind.example/engineering").respond(404)
        mock.get("https://www.northwind.example/remote-work").respond(
            200, html="<p>Remote-first.</p>"
        )
        pages = await reader().read(SITE)
    urls = [p.url for p in pages]
    assert urls[0] == SITE
    assert "https://www.northwind.example/about" in urls
    assert "founded in 2015" in next(p.text for p in pages if p.url.endswith("/about"))
    assert not blocked.called
    assert all("blog.northwind.example" not in u for u in urls)  # 404 pages are skipped


@pytest.mark.asyncio
async def test_a_page_that_redirects_off_the_domain_is_dropped() -> None:
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://www.northwind.example/robots.txt").respond(404)
        mock.get(SITE).respond(
            200, html='<p>Northwind builds billing software.</p><a href="/about">About</a>'
        )
        mock.get("https://www.northwind.example/about").respond(
            302, headers={"location": "https://other.example/about"}
        )
        mock.get("https://other.example/about").respond(200, html="<p>Other company</p>")
        pages = await reader().read(SITE)
    assert [p.url for p in pages] == [SITE]


@pytest.mark.asyncio
async def test_unreachable_home_returns_nothing() -> None:
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://www.northwind.example/robots.txt").respond(404)
        mock.get(SITE).respond(503)
        assert await reader().read(SITE) == []


PAGE = """<html><head><title>Northwind | Home</title><style>.x{}</style></head><body>
<header><a href="/">Logo</a><nav><a href="/p">Products</a></nav></header>
<iframe src="https://tracker.example"></iframe>
<main><h1>Billing for telecoms</h1><p>Northwind builds billing software for telecom operators
across Europe and has teams working remotely.</p><ul><li>Fast</li></ul>
<form><p>Thank you for signing up for our newsletter, we will be in touch.</p></form></main>
<footer><p>Cookie settings and legal notices apply to every page of this website.</p></footer>
</body></html>"""


def test_page_text_keeps_the_main_content_without_menus_forms_and_footers() -> None:
    text = page_text(PAGE)
    assert "Northwind builds billing software for telecom operators" in text
    assert "Billing for telecoms" in text
    for noise in ("Products", "Logo", "newsletter", "Cookie settings", "tracker.example", ".x{}"):
        assert noise not in text


def test_page_text_drops_short_menu_like_lines_but_keeps_sentences() -> None:
    html = "<body><div><p>Back</p><p>-</p><p>Products</p><p>We pay every employee on time.</p></div></body>"
    assert page_text(html) == "We pay every employee on time."


def test_page_text_of_an_empty_page_is_empty() -> None:
    assert page_text("") == ""

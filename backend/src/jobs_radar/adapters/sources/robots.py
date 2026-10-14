"""``robots.txt`` for the adapters that read a company's own pages (ADR-054, ADR-070).

One gate per client: it fetches ``/robots.txt`` once per origin through the guarded client, answers
"may this address be read by an automated client", and lists the ``Sitemap:`` entries. An
unreadable ``robots.txt`` allows the page (the usual convention); an explicit refusal is respected
and never worked around.
"""

from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from jobs_radar.core.http import FetchError, GuardedHttpClient

_ROBOTS_BYTES = 500_000


class RobotsGate:
    """Caches the parsed ``robots.txt`` of each origin for the life of one detection or run."""

    def __init__(self, client: GuardedHttpClient) -> None:
        self._client = client
        self._parsed: dict[str, tuple[RobotFileParser | None, list[str]]] = {}

    async def _origin(self, url: str) -> tuple[RobotFileParser | None, list[str]]:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._parsed:
            parser: RobotFileParser | None = None
            sitemaps: list[str] = []
            try:
                response = await self._client.get(f"{origin}/robots.txt")
            except FetchError:
                response = None
            if (
                response is not None
                and response.status == 200
                and len(response.body) < _ROBOTS_BYTES
            ):
                lines = response.body.decode("utf-8", "replace").splitlines()
                parser = RobotFileParser()
                parser.parse(lines)
                for line in lines:
                    name, _, value = line.partition(":")
                    if name.strip().lower() == "sitemap" and value.strip().startswith("http"):
                        sitemaps.append(value.strip())
            self._parsed[origin] = (parser, sitemaps)
        return self._parsed[origin]

    async def allowed(self, url: str) -> bool:
        """Whether the site's ``robots.txt`` lets an automated client read ``url``."""
        parser, _ = await self._origin(url)
        return parser is None or parser.can_fetch("*", url)

    async def sitemaps(self, url: str) -> list[str]:
        """Return the ``Sitemap:`` addresses the origin of ``url`` declares."""
        _, sitemaps = await self._origin(url)
        return list(sitemaps)

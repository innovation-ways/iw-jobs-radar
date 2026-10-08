"""Wikipedia summary adapter: a short description under CC BY-SA 4.0 with attribution (F4)."""

from dataclasses import dataclass
from urllib.parse import quote

from jobs_radar.adapters.enrichment.base import PublicApi

API = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
LICENCE = "CC-BY-SA-4.0"


@dataclass(frozen=True)
class WikipediaSummary:
    """The extract of an article and what is needed to attribute it."""

    title: str
    text: str
    url: str
    licence: str = LICENCE


class WikipediaAdapter:
    """Reads the summary of one article."""

    def __init__(self, api: PublicApi) -> None:
        self._api = api

    async def summary(self, title: str) -> WikipediaSummary | None:
        """Return the summary of the article ``title``, or ``None`` if there is none."""
        slug = quote(title.replace(" ", "_"), safe="_")
        data = await self._api.get_json(API.format(slug), allow_not_found=True)
        if not data or not data.get("extract"):
            return None
        page = ((data.get("content_urls") or {}).get("desktop") or {}).get("page")
        return WikipediaSummary(
            title=str(data.get("title", title)),
            text=" ".join(str(data["extract"]).split()),
            url=str(page or f"https://en.wikipedia.org/wiki/{slug}"),
        )

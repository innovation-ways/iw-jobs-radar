"""GitHub organisation adapter: website and technology hints (F6).

Anonymous requests are limited to 60 an hour, so only two calls are made per organisation. An
optional token raises the limit; it is sent only to api.github.com and never returned or logged.
"""

from collections import Counter
from dataclasses import dataclass
from urllib.parse import quote

from jobs_radar.adapters.enrichment.base import PublicApi

API = "https://api.github.com"
LICENCE = "GitHub Terms of Service (public data)"


@dataclass(frozen=True)
class GitHubOrg:
    """What an organisation page tells about the company."""

    login: str
    website: str | None
    description: str | None
    public_repos: int
    languages: list[str]
    url: str
    licence: str = LICENCE


class GitHubAdapter:
    """Reads one organisation and the languages of its most recent repositories."""

    def __init__(self, api: PublicApi, *, token: str | None = None) -> None:
        self._api = api
        self._token = token

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def organisation(self, login: str) -> GitHubOrg | None:
        """Return the organisation ``login`` or ``None`` if it does not exist."""
        slug = quote(login, safe="-_.")
        org = await self._api.get_json(
            f"{API}/orgs/{slug}", headers=self._headers(), allow_not_found=True
        )
        if not org:
            return None
        repos = await self._api.get_json(
            f"{API}/orgs/{slug}/repos",
            {"per_page": "30", "sort": "pushed", "type": "public"},
            headers=self._headers(),
            allow_not_found=True,
        )
        counts = Counter(
            r["language"] for r in (repos or []) if isinstance(r, dict) and r.get("language")
        )
        return GitHubOrg(
            login=str(org.get("login", login)),
            website=(str(org["blog"]).strip() or None) if org.get("blog") else None,
            description=org.get("description"),
            public_repos=int(org.get("public_repos") or 0),
            languages=[name for name, _ in counts.most_common(5)],
            url=str(org.get("html_url") or f"https://github.com/{slug}"),
        )

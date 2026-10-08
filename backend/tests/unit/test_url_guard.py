"""SSRF protection for every outbound URL (ADR-035, TR-4.5)."""

import pytest

from jobs_radar.core.url_guard import BlockedUrlError, UrlGuard

PUBLIC = "93.184.216.34"


def resolver(mapping: dict[str, list[str]]):  # type: ignore[no-untyped-def]
    async def resolve(host: str) -> list[str]:
        if host not in mapping:
            raise OSError(f"cannot resolve {host}")
        return mapping[host]

    return resolve


async def check(url: str, mapping: dict[str, list[str]] | None = None, **options: object) -> None:
    guard = UrlGuard(resolver=resolver(mapping or {"boards.example.test": [PUBLIC]}), **options)  # type: ignore[arg-type]
    await guard.check(url)


async def test_a_public_https_url_is_allowed() -> None:
    await check("https://boards.example.test/v1/boards/x/jobs")


@pytest.mark.parametrize(
    "url",
    [
        "http://boards.example.test/x",
        "ftp://boards.example.test/x",
        "file:///etc/passwd",
        "//boards.example.test/x",
    ],
)
async def test_only_https_is_allowed(url: str) -> None:
    with pytest.raises(BlockedUrlError, match="https"):
        await check(url)


async def test_credentials_in_the_url_are_rejected() -> None:
    with pytest.raises(BlockedUrlError, match=r"(?i)credentials"):
        await check("https://user:secret@boards.example.test/x")


async def test_a_missing_host_is_rejected() -> None:
    with pytest.raises(BlockedUrlError):
        await check("https:///path")


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",  # loopback
        "10.1.2.3",
        "172.16.0.5",
        "192.168.0.104",  # private ranges (the owner's LAN)
        "169.254.169.254",  # cloud metadata service (link-local)
        "100.109.170.23",  # carrier-grade NAT range used by Tailscale
        "0.0.0.0",  # unspecified
        "224.0.0.1",  # multicast
        "::1",
        "fe80::1",
        "fd00::1",  # IPv6 loopback, link-local, unique local
        "::ffff:127.0.0.1",  # IPv4-mapped loopback must not slip through
    ],
)
async def test_non_public_addresses_are_blocked_as_literals(address: str) -> None:
    host = f"[{address}]" if ":" in address else address
    with pytest.raises(BlockedUrlError, match="not a public address"):
        await check(f"https://{host}/x")


async def test_a_name_that_resolves_to_a_private_address_is_blocked() -> None:
    with pytest.raises(BlockedUrlError, match="not a public address"):
        await check("https://internal.example.test/x", {"internal.example.test": ["10.0.0.7"]})


async def test_one_private_answer_among_public_ones_blocks_the_name() -> None:
    # A name with several A records is as dangerous as its worst answer (DNS rebinding tricks).
    with pytest.raises(BlockedUrlError):
        await check("https://mixed.example.test/x", {"mixed.example.test": [PUBLIC, "127.0.0.1"]})


async def test_localhost_and_metadata_names_are_blocked_without_resolving() -> None:
    for host in ("localhost", "metadata.google.internal", "LOCALHOST"):
        with pytest.raises(BlockedUrlError):
            await check(f"https://{host}/x", {})


async def test_an_unresolvable_name_is_blocked() -> None:
    with pytest.raises(BlockedUrlError, match="resolve"):
        await check("https://nowhere.example.test/x", {})


async def test_local_targets_need_an_explicit_policy_and_an_allowed_host() -> None:
    mapping = {"ollama.lan": ["192.168.0.104"]}
    with pytest.raises(BlockedUrlError):
        await check("https://ollama.lan/x", mapping)
    with pytest.raises(BlockedUrlError):  # policy on, but the host is not on the allow-list
        await check("https://ollama.lan/x", mapping, allow_private=True)
    await check(
        "https://ollama.lan/x",
        mapping,
        allow_private=True,
        allowed_private_hosts=frozenset({"ollama.lan"}),
    )


async def test_the_local_policy_never_unlocks_link_local_or_metadata() -> None:
    mapping = {"meta.lan": ["169.254.169.254"]}
    with pytest.raises(BlockedUrlError):
        await check(
            "https://meta.lan/x",
            mapping,
            allow_private=True,
            allowed_private_hosts=frozenset({"meta.lan"}),
        )

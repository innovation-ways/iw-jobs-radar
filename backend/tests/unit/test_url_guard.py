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


LOCAL = {
    "allow_private": True,
    "allowed_private_hosts": frozenset({"host.docker.internal", "127.0.0.1", "localhost"}),
}


async def test_an_explicitly_allowed_local_host_may_use_plain_http() -> None:
    mapping = {"host.docker.internal": ["172.17.0.1"]}
    await check("http://host.docker.internal:11434/api/chat", mapping, **LOCAL)
    await check("http://127.0.0.1:11434/api/chat", {}, **LOCAL)
    await check("http://localhost:11434/api/chat", {"localhost": ["127.0.0.1"]}, **LOCAL)


async def test_plain_http_to_a_local_host_needs_the_policy_and_the_allow_list() -> None:
    mapping = {"host.docker.internal": ["172.17.0.1"]}
    with pytest.raises(BlockedUrlError):  # policy off
        await check("http://host.docker.internal:11434/x", mapping)
    with pytest.raises(BlockedUrlError):  # policy on, host not listed
        await check("http://host.docker.internal:11434/x", mapping, allow_private=True)


async def test_plain_http_stays_blocked_for_hosts_that_are_not_allowed_local_targets() -> None:
    with pytest.raises(BlockedUrlError, match="https"):
        await check("http://boards.example.test/x", None, **LOCAL)


async def test_an_allowed_local_name_may_be_internal_but_an_unlisted_one_may_not() -> None:
    await check("https://host.docker.internal/x", {"host.docker.internal": ["172.17.0.1"]}, **LOCAL)
    with pytest.raises(BlockedUrlError):
        await check(
            "https://metadata.google.internal/x",
            {"metadata.google.internal": ["10.0.0.1"]},
            **LOCAL,
        )
    with pytest.raises(BlockedUrlError):
        await check(
            "http://localhost:11434/x", {"localhost": ["127.0.0.1"]}
        )  # needs the allow-list too


async def test_a_listed_local_host_pointing_at_link_local_is_still_blocked_over_http() -> None:
    with pytest.raises(BlockedUrlError):
        await check(
            "http://host.docker.internal/x",
            {"host.docker.internal": ["169.254.169.254"]},
            **LOCAL,
        )

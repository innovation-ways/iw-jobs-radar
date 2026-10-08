"""SSRF protection: decide whether an outbound URL may be requested (ADR-035, TR-4.5).

Rules: HTTPS only; no credentials in the URL; the host must resolve, and **every** address it
resolves to must be a public one. Private, loopback, link-local (including the cloud metadata
service), carrier-grade NAT (the Tailscale range), multicast, reserved and unspecified addresses
are refused. Local targets such as a local Ollama server are allowed only when the deployment
policy says so *and* the host is on an explicit allow-list; link-local addresses are never allowed.

Resolution is checked when the request is made and again for every redirect. A name that changes
its answer between this check and the connection (DNS rebinding) is a known limitation of checking
before connecting; the only targets reachable that way are still subject to this check on retry.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

Resolver = Callable[[str], Awaitable[list[str]]]

# Names that are internal by definition, refused without a DNS lookup.
_BLOCKED_NAMES = frozenset({"localhost", "metadata", "metadata.google.internal"})
_BLOCKED_SUFFIXES = (".localhost", ".internal")


class BlockedUrlError(Exception):
    """Raised when a URL must not be requested. The message is safe to show to the owner."""


async def system_resolver(host: str) -> list[str]:
    """Resolve ``host`` with the operating system; raises ``OSError`` when it cannot."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


def _unwrap(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Return the IPv4 address inside an IPv4-mapped IPv6 address, otherwise the address itself."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return address.is_global and not (address.is_multicast or address.is_reserved)


class UrlGuard:
    """Validates URLs before they are requested."""

    def __init__(
        self,
        *,
        resolver: Resolver = system_resolver,
        allow_private: bool = False,
        allowed_private_hosts: frozenset[str] = frozenset(),
    ) -> None:
        self._resolver = resolver
        self._allow_private = allow_private
        self._allowed_private_hosts = frozenset(host.lower() for host in allowed_private_hosts)

    async def check(self, url: str) -> None:
        """Raise :class:`BlockedUrlError` unless ``url`` may be requested."""
        try:
            parts = urlsplit(url)
        except ValueError as exc:
            msg = "The URL is not valid."
            raise BlockedUrlError(msg) from exc
        if parts.scheme.lower() != "https":
            msg = "Only https URLs are allowed."
            raise BlockedUrlError(msg)
        if parts.username or parts.password:
            msg = "Credentials inside the URL are not allowed."
            raise BlockedUrlError(msg)
        host = (parts.hostname or "").lower().rstrip(".")
        if not host:
            msg = "The URL has no host."
            raise BlockedUrlError(msg)
        if host in _BLOCKED_NAMES or host.endswith(_BLOCKED_SUFFIXES):
            msg = f"{host} is not a public address."
            raise BlockedUrlError(msg)

        for address in await self._addresses(host):
            self._check_address(address, host)

    async def _addresses(self, host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        try:
            return [ipaddress.ip_address(host)]
        except ValueError:
            pass  # not a literal address: resolve the name
        try:
            resolved = await self._resolver(host)
        except OSError as exc:
            msg = f"The host {host} could not be resolved."
            raise BlockedUrlError(msg) from exc
        if not resolved:
            msg = f"The host {host} could not be resolved."
            raise BlockedUrlError(msg)
        return [ipaddress.ip_address(item) for item in resolved]

    def _check_address(
        self, address: ipaddress.IPv4Address | ipaddress.IPv6Address, host: str
    ) -> None:
        address = _unwrap(address)
        # Link-local covers the cloud metadata service (169.254.169.254): never allowed.
        if address.is_link_local:
            msg = f"{host} is not a public address (link-local addresses are always blocked)."
            raise BlockedUrlError(msg)
        if _is_public(address):
            return
        if self._allow_private and host in self._allowed_private_hosts:
            return
        msg = f"{host} is not a public address."
        raise BlockedUrlError(msg)

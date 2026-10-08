"""The test session must block real network access (ADR-035)."""

import socket

import pytest
from pytest_socket import SocketConnectBlockedError


@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_real_outbound_connection_is_blocked() -> None:
    with pytest.raises(SocketConnectBlockedError):
        # A routable public address: if the block is missing this would attempt a real connection.
        socket.create_connection(("93.184.216.34", 80), timeout=1)


def test_loopback_is_allowed() -> None:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    client = socket.create_connection(server.getsockname(), timeout=1)
    client.close()
    server.close()

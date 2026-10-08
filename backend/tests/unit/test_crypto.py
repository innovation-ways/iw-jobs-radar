"""Credential encryption (ADR-033): round trip, wrong key, missing key, no plaintext leakage."""

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from jobs_radar.core.crypto import CredentialBox, CredentialKeyError


def key() -> SecretStr:
    return SecretStr(Fernet.generate_key().decode())


def test_a_secret_round_trips_and_the_ciphertext_hides_it() -> None:
    box = CredentialBox(key())
    token = box.encrypt("sk-test-123456")
    assert isinstance(token, bytes) and b"sk-test" not in token
    assert box.decrypt(token) == "sk-test-123456"


def test_encrypting_twice_gives_different_ciphertext() -> None:
    box = CredentialBox(key())
    assert box.encrypt("same") != box.encrypt("same")


def test_a_different_key_cannot_decrypt() -> None:
    token = CredentialBox(key()).encrypt("secret")
    with pytest.raises(CredentialKeyError, match="key"):
        CredentialBox(key()).decrypt(token)


def test_a_missing_or_malformed_key_is_refused_without_echoing_it() -> None:
    with pytest.raises(CredentialKeyError, match="JOBS_RADAR_CREDENTIAL_KEY"):
        CredentialBox(None)
    with pytest.raises(CredentialKeyError) as caught:
        CredentialBox(SecretStr("not-a-valid-key"))
    assert "not-a-valid-key" not in str(caught.value)


def test_an_empty_secret_is_refused() -> None:
    with pytest.raises(ValueError, match="empty"):
        CredentialBox(key()).encrypt("   ")


def test_the_box_never_shows_its_key() -> None:
    k = key()
    assert k.get_secret_value() not in repr(CredentialBox(k))

"""Encryption of stored credentials (ADR-013, ADR-033).

Fernet with the key from ``JOBS_RADAR_CREDENTIAL_KEY``. The ciphertext goes in a dedicated column,
never in JSON. Losing the key makes stored credentials unrecoverable; they must be entered again.
"""

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr


class CredentialKeyError(Exception):
    """The credential key is missing, malformed or does not match the stored data."""


class CredentialBox:
    """Encrypts and decrypts short secrets such as API keys."""

    def __init__(self, key: SecretStr | None) -> None:
        if key is None or not key.get_secret_value().strip():
            msg = "JOBS_RADAR_CREDENTIAL_KEY is not set, so credentials cannot be stored."
            raise CredentialKeyError(msg)
        try:
            self._fernet = Fernet(key.get_secret_value().strip().encode())
        except ValueError as exc:
            # Never echo the key: the message is generic.
            msg = "JOBS_RADAR_CREDENTIAL_KEY is not a valid key."
            raise CredentialKeyError(msg) from exc

    def __repr__(self) -> str:
        return "CredentialBox()"

    def encrypt(self, secret: str) -> bytes:
        """Return the ciphertext of ``secret`` (a non-empty string)."""
        if not secret.strip():
            msg = "The secret is empty."
            raise ValueError(msg)
        return self._fernet.encrypt(secret.strip().encode())

    def decrypt(self, token: bytes) -> str:
        """Return the secret, or raise :class:`CredentialKeyError` if the key does not match."""
        try:
            return self._fernet.decrypt(token).decode()
        except InvalidToken as exc:
            msg = "The stored credential cannot be read with the current credential key."
            raise CredentialKeyError(msg) from exc

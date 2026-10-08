"""Optional integration credentials, for now the GitHub token (T7, ADR-033).

The token only raises GitHub's anonymous request limit for company enrichment. It is encrypted,
accepted by a write endpoint only and never returned; without it (or without the credential key)
enrichment simply runs anonymously.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.crypto import CredentialBox, CredentialKeyError
from jobs_radar.core.errors import DependencyUnavailableError, InputValidationError
from jobs_radar.db.models import IntegrationCredential

KNOWN = ("github",)


class IntegrationService:
    """Stores and reads integration credentials. The caller owns the transaction."""

    def __init__(self, session: AsyncSession, *, box: CredentialBox | None) -> None:
        self._session = session
        self._box = box

    @staticmethod
    def _check(name: str) -> None:
        if name not in KNOWN:
            msg = f"Unknown integration '{name}'."
            raise InputValidationError(msg)

    async def _row(self, owner_id: int, name: str) -> IntegrationCredential | None:
        return (
            await self._session.execute(
                select(IntegrationCredential).where(
                    IntegrationCredential.owner_id == owner_id, IntegrationCredential.name == name
                )
            )
        ).scalar_one_or_none()

    async def status(self, owner_id: int) -> dict[str, str]:
        """Return ``saved`` or ``none`` for each integration (never the credential)."""
        result = dict.fromkeys(KNOWN, "none")
        rows = await self._session.execute(
            select(IntegrationCredential).where(IntegrationCredential.owner_id == owner_id)
        )
        for row in rows.scalars():
            if row.credential_ciphertext and row.name in result:
                result[row.name] = "saved"
        return result

    async def set_token(self, owner_id: int, name: str, secret: str) -> None:
        """Encrypt and store the credential, replacing any earlier one."""
        self._check(name)
        if not secret.strip():
            msg = "The credential is empty."
            raise InputValidationError(msg)
        if self._box is None:
            msg = "JOBS_RADAR_CREDENTIAL_KEY is not configured, so credentials cannot be stored."
            raise DependencyUnavailableError(msg)
        row = await self._row(owner_id, name)
        if row is None:
            row = IntegrationCredential(owner_id=owner_id, name=name)
            self._session.add(row)
        row.credential_ciphertext = self._box.encrypt(secret)
        row.credential_updated_at = datetime.now(UTC)
        await self._session.flush()

    async def clear_token(self, owner_id: int, name: str) -> None:
        """Delete the stored credential."""
        self._check(name)
        row = await self._row(owner_id, name)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    async def token(self, owner_id: int, name: str) -> str | None:
        """Return the decrypted credential for server-side use, or ``None``."""
        row = await self._row(owner_id, name)
        if row is None or not row.credential_ciphertext or self._box is None:
            return None
        try:
            return self._box.decrypt(row.credential_ciphertext)
        except CredentialKeyError:
            return None

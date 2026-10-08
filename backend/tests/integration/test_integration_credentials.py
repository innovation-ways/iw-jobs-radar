"""Optional integration credentials (GitHub token): encrypted, write-only (T7, ADR-033)."""

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.crypto import CredentialBox
from jobs_radar.core.errors import DependencyUnavailableError, InputValidationError
from jobs_radar.db.models import IntegrationCredential
from jobs_radar.services.integrations import IntegrationService

pytestmark = pytest.mark.integration

TOKEN = "ghp_integration_secret_value"


def box() -> CredentialBox:
    return CredentialBox(SecretStr(Fernet.generate_key().decode()))


@pytest.fixture(autouse=True)
async def clean(db_session: AsyncSession) -> None:
    await db_session.execute(delete(IntegrationCredential))


async def test_a_token_is_stored_encrypted_and_only_its_status_is_visible(
    db_session: AsyncSession,
) -> None:
    service = IntegrationService(db_session, box=box())
    assert await service.status(1) == {"github": "none"}
    await service.set_token(1, "github", TOKEN)
    stored = (await db_session.execute(select(IntegrationCredential))).scalar_one()
    assert (
        stored.credential_ciphertext is not None
        and TOKEN.encode() not in stored.credential_ciphertext
    )
    assert await service.status(1) == {"github": "saved"}
    assert await service.token(1, "github") == TOKEN
    await service.clear_token(1, "github")
    assert (
        await service.status(1) == {"github": "none"} and await service.token(1, "github") is None
    )


async def test_replacing_a_token_keeps_one_row(db_session: AsyncSession) -> None:
    service = IntegrationService(db_session, box=box())
    await service.set_token(1, "github", TOKEN)
    await service.set_token(1, "github", TOKEN + "2")
    assert len((await db_session.execute(select(IntegrationCredential))).scalars().all()) == 1
    assert await service.token(1, "github") == TOKEN + "2"


async def test_unknown_integrations_empty_secrets_and_a_missing_key_are_refused(
    db_session: AsyncSession,
) -> None:
    service = IntegrationService(db_session, box=box())
    with pytest.raises(InputValidationError):
        await service.set_token(1, "twitter", TOKEN)
    with pytest.raises(InputValidationError, match="empty"):
        await service.set_token(1, "github", "  ")
    with pytest.raises(DependencyUnavailableError, match="JOBS_RADAR_CREDENTIAL_KEY"):
        await IntegrationService(db_session, box=None).set_token(1, "github", TOKEN)
    # reading without a key simply yields no token (enrichment then runs anonymously)
    assert await IntegrationService(db_session, box=None).token(1, "github") is None

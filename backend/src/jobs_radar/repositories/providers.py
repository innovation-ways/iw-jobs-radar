"""Data access for AI provider connections and the privacy setting."""

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models import PrivacySetting, ProviderConnection


class ProviderRepository:
    """Reads and writes ``provider_connection`` and ``privacy_setting``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, owner_id: int) -> list[ProviderConnection]:
        """Return the owner's connections, oldest first."""
        rows = await self._session.execute(
            select(ProviderConnection)
            .where(ProviderConnection.owner_id == owner_id)
            .order_by(ProviderConnection.provider_connection_id)
        )
        return list(rows.scalars())

    async def get(
        self, owner_id: int, provider_connection_id: int, *, for_update: bool = False
    ) -> ProviderConnection | None:
        """Return one connection of the owner, or ``None``."""
        statement = select(ProviderConnection).where(
            ProviderConnection.owner_id == owner_id,
            ProviderConnection.provider_connection_id == provider_connection_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def add(self, connection: ProviderConnection) -> ProviderConnection:
        """Insert a connection and load its server-side defaults."""
        self._session.add(connection)
        await self._session.flush()
        await self._session.refresh(connection)
        return connection

    async def delete(self, connection: ProviderConnection) -> None:
        """Delete a connection (and with it the encrypted credential)."""
        await self._session.delete(connection)
        await self._session.flush()

    async def clear_flag(self, owner_id: int, flag: str) -> None:
        """Unset ``is_active`` or ``use_for_jobs`` on every connection of the owner."""
        await self._session.execute(
            update(ProviderConnection)
            .where(ProviderConnection.owner_id == owner_id)
            .values({flag: False})
        )
        await self._session.flush()
        self._session.expire_all()

    async def privacy(self, owner_id: int) -> tuple[PrivacySetting, bool]:
        """Return the privacy setting and whether it was just created (first use)."""
        created = (
            await self._session.execute(
                insert(PrivacySetting)
                .values(owner_id=owner_id)
                .on_conflict_do_nothing(index_elements=["owner_id"])
                .returning(PrivacySetting.privacy_setting_id)
            )
        ).scalar_one_or_none() is not None
        setting = (
            await self._session.execute(
                select(PrivacySetting)
                .where(PrivacySetting.owner_id == owner_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        return setting, created

    async def delete_all(self, owner_id: int) -> None:
        """Remove every connection of the owner."""
        await self._session.execute(
            delete(ProviderConnection).where(ProviderConnection.owner_id == owner_id)
        )

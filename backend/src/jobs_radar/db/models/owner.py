"""The owner of personal data. V1 has a single fixed local owner (ADR-009)."""

from sqlalchemy.orm import Mapped

from jobs_radar.db.base import Base, TimestampMixin
from jobs_radar.db.columns import pk_column, text_column


class Owner(TimestampMixin, Base):
    """A person who owns profiles, intents, sources and inbox decisions.

    Authentication does not exist in V1, but every personal table is scoped by ``owner_id`` so
    that adding users later needs no data migration.
    """

    __tablename__ = "owner"
    __table_args__ = {"comment": "Owner of personal data; V1 has one fixed local owner."}

    owner_id: Mapped[int] = pk_column("Surrogate primary key of the owner.")
    display_name: Mapped[str] = text_column("Human-readable name of the owner.", length=100)

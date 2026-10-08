"""Worker liveness tracking used by ``/readyz`` and the Sources screen (ADR-031)."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, String
from sqlalchemy.orm import Mapped, mapped_column

from jobs_radar.db.base import Base, TimestampMixin


class WorkerHeartbeat(TimestampMixin, Base):
    """One row per worker process name, refreshed on every worker loop iteration.

    Readiness reports the worker as ``stale`` when ``beat_at`` is older than the configured
    maximum age, and as ``missing`` when no row exists.
    """

    __tablename__ = "worker_heartbeat"
    # SQLAlchemy declarative convention: a plain dict is required here.
    __table_args__ = {  # noqa: RUF012
        "comment": "Liveness of worker processes, refreshed every loop iteration."
    }

    worker_heartbeat_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=False),
        primary_key=True,
        comment="Surrogate primary key of the heartbeat row.",
    )
    worker_name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        comment="Logical name of the worker process that owns this heartbeat.",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="UTC time at which the current worker process started.",
    )
    beat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="UTC time of the most recent heartbeat.",
    )

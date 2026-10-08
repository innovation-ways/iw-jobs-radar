"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from jobs_radar.db.models.worker import WorkerHeartbeat

__all__ = ["WorkerHeartbeat"]

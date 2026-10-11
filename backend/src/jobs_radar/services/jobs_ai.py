"""The worker's job-analysis setup, read from the database (ADR-046).

The connection marked ``use_for_jobs`` (always a local model) decides which model extracts and
scores collected jobs. It is read on every worker iteration, so a change in the AI & privacy screen
applies without a restart; the environment only seeded the first connection. The setup is rebuilt
only when the connection changes. Without such a connection the answer is ``None`` (No AI): jobs
are still collected, grouped and listed as "not evaluated".
"""

from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jobs_radar.adapters.providers.factory import ProviderSpec, build_provider
from jobs_radar.adapters.providers.ollama import build_ollama_embedder
from jobs_radar.core.settings import Settings
from jobs_radar.db.models import ProviderConnection
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.services.dedup import DedupRunner
from jobs_radar.services.direction_service import DirectionRunner
from jobs_radar.services.evaluation import EvaluationRunner
from jobs_radar.services.extraction_queue import ExtractionQueue
from jobs_radar.services.job_summary import SummaryRunner


@dataclass(frozen=True)
class JobsAi:
    """The runners that need a model."""

    extraction: ExtractionQueue
    evaluation: EvaluationRunner
    directions: DirectionRunner
    summaries: SummaryRunner
    dedup: DedupRunner
    model: str
    embedding_model: str
    # The local model that judges career directions (the job model unless another is chosen).
    direction_model: str = ""


class JobsAiLoader:
    """Loads (and caches) the job-analysis setup from the active local connection."""

    def __init__(
        self, settings: Settings, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._key: tuple[int, int, str, str, str, str] | None = None
        self._current: JobsAi | None = None

    async def load(self) -> JobsAi | None:
        """Return the setup for the connection in use, or ``None`` for No AI."""
        async with self._session_factory() as session:
            connection = (
                await session.execute(
                    select(ProviderConnection).where(
                        ProviderConnection.owner_id == LOCAL_OWNER_ID,
                        ProviderConnection.use_for_jobs.is_(True),
                    )
                )
            ).scalar_one_or_none()
        if connection is None or not connection.model_id or not connection.endpoint_url:
            self._key, self._current = None, None
            return None
        embedding = str(
            (connection.config_json or {}).get("embedding_model") or self._settings.embedding_model
        )
        direction_model = str(
            (connection.config_json or {}).get("direction_model") or connection.model_id
        )
        key = (
            connection.provider_connection_id,
            connection.version,
            connection.endpoint_url,
            connection.model_id,
            embedding,
            direction_model,
        )
        if key != self._key or self._current is None:
            self._current = self._build(
                connection,
                embedding,
                connection.endpoint_url,
                connection.model_id,
                direction_model,
            )
            self._key = key
        return self._current

    def _build(
        self,
        connection: ProviderConnection,
        embedding_model: str,
        endpoint: str,
        model: str,
        direction_model: str,
    ) -> JobsAi:
        # A local connection may only use the host the deployment configured (ADR-035).
        host = urlsplit(self._settings.ollama_url).hostname
        spec = ProviderSpec("ollama", endpoint, model)
        provider = build_provider(spec, self._settings)
        if urlsplit(endpoint).hostname != host:
            msg = "The local connection does not match the configured local server."
            raise ValueError(msg)
        direction_provider = (
            provider
            if direction_model == model
            else build_provider(ProviderSpec("ollama", endpoint, direction_model), self._settings)
        )
        embedder = build_ollama_embedder(self._settings, model=embedding_model)
        return JobsAi(
            extraction=ExtractionQueue(
                self._session_factory, provider, max_chars=self._settings.extraction_max_chars
            ),
            evaluation=EvaluationRunner(self._session_factory, provider),
            directions=DirectionRunner(
                self._session_factory,
                direction_provider,
                max_chars=self._settings.extraction_max_chars,
            ),
            # Prose that must stay faithful to the posting needs the larger local model the owner
            # chose for directions (the job model unless another is set): on a small model the
            # summaries invented details (ADR-059).
            summaries=SummaryRunner(
                self._session_factory,
                direction_provider,
                max_chars=self._settings.extraction_max_chars,
            ),
            dedup=DedupRunner(self._session_factory, embedder),
            model=model,
            embedding_model=embedding_model,
            direction_model=direction_model,
        )

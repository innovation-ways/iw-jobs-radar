"""Collecting a job board: company per posting, derived scope, truncated runs and the run interval
(ADR-049, T9.3)."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import make_intent, make_profile
from tests.fake_adapter import FakeAdapter, listing, make_posting

from jobs_radar.adapters.sources.base import SourceCheckpoint
from jobs_radar.adapters.sources.catalogue import require_entry
from jobs_radar.core.crypto import CredentialBox
from jobs_radar.core.errors import ConflictError
from jobs_radar.db.models import (
    CollectionRun,
    Company,
    JobPosting,
    SearchIntent,
    SourceConfiguration,
    SourceRunResult,
)
from jobs_radar.domain.enums import (
    LOCAL_OWNER_ID,
    RunStatus,
    SourceErrorClass,
    SourceOutcome,
    SourceType,
)
from jobs_radar.services.collection import CollectionService
from jobs_radar.services.sources import SourceService

pytestmark = pytest.mark.integration

T0 = datetime(2026, 10, 9, 7, 30, tzinfo=UTC)


class Clock:
    """A controllable clock."""

    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture(autouse=True)
async def _our_intent_only(db_session: AsyncSession) -> None:
    """The owner has one enabled intent (Portugal, remote from the EU); other tests' are off."""
    await db_session.execute(update(SearchIntent).values(enabled=False))
    await db_session.execute(update(SourceConfiguration).values(enabled=False))
    profile, _ = await make_profile(db_session)
    intent, _ = await make_intent(db_session, profile)
    intent.enabled = True
    await db_session.flush()


def build(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, adapter: FakeAdapter, clock: Clock
) -> CollectionService:
    monkeypatch.setattr(session, "commit", session.flush)

    @asynccontextmanager
    async def same_session() -> AsyncIterator[AsyncSession]:
        yield session

    factory: Callable[[], object] = same_session
    return CollectionService(factory, {SourceType.HIMALAYAS: adapter}, clock=clock)  # type: ignore[arg-type]


async def board(session: AsyncSession) -> SourceConfiguration:
    """A Himalayas job board source: no company of its own, no config yet."""
    entry = require_entry("himalayas")
    source = SourceConfiguration(
        owner_id=LOCAL_OWNER_ID,
        company_id=None,
        source_type=SourceType.HIMALAYAS.value,
        external_identifier=entry.catalogue_key,
        display_name=entry.display_name,
        url=entry.endpoint,
        config_json={},
    )
    session.add(source)
    await session.flush()
    return source


async def run(service: CollectionService, source: SourceConfiguration) -> CollectionRun:
    queued = await service.request_run(
        LOCAL_OWNER_ID, source_configuration_id=source.source_configuration_id
    )
    await service.execute_run(queued.collection_run_id)
    return queued


async def last_result(session: AsyncSession, source: SourceConfiguration) -> SourceRunResult:
    return (
        (
            await session.execute(
                select(SourceRunResult)
                .where(SourceRunResult.source_configuration_id == source.source_configuration_id)
                .order_by(SourceRunResult.source_run_result_id.desc())
            )
        )
        .scalars()
        .first()
    )  # type: ignore[return-value]


async def postings_of(session: AsyncSession, source: SourceConfiguration) -> list[JobPosting]:
    rows = await session.execute(
        select(JobPosting)
        .where(JobPosting.source_configuration_id == source.source_configuration_id)
        .order_by(JobPosting.external_job_id)
    )
    return list(rows.scalars())


# --- companies, filters and scope -------------------------------------------------------------


async def test_each_posting_belongs_to_the_company_it_names(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    adapter = FakeAdapter(
        [
            listing(
                make_posting("1", company_name="Acme Robotics"),
                make_posting("2", company_name="Globex Labs"),
                make_posting("3", company_name="Acme Robotics"),
            )
        ]
    )
    source = await board(db_session)
    await run(build(db_session, monkeypatch, adapter, clock), source)
    postings = await postings_of(db_session, source)
    names = {
        p.external_job_id: (await db_session.get(Company, p.company_id)).canonical_name  # type: ignore[union-attr]
        for p in postings
    }
    assert names == {"1": "Acme Robotics", "2": "Globex Labs", "3": "Acme Robotics"}
    assert postings[0].company_id == postings[2].company_id
    assert (await last_result(db_session, source)).new_count == 3


async def test_the_adapter_receives_the_catalogue_filters_and_the_derived_scope(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    seen: list[SourceCheckpoint] = []

    def provider(checkpoint: SourceCheckpoint) -> object:
        seen.append(checkpoint)
        return listing(make_posting("1", company_name="Acme Robotics"))

    adapter = FakeAdapter(provider=provider)
    source = await board(db_session)
    await run(build(db_session, monkeypatch, adapter, clock), source)
    checkpoint = seen[0]
    # A board with no stored filters selects every area of the owner's packs (the software pack).
    assert checkpoint.filters == require_entry("himalayas").default_filters.model_copy(
        update={"categories": ["software", "data", "devops", "security", "telecom"]}
    )
    assert checkpoint.scope is not None
    assert {"PT", "GB"} <= checkpoint.scope.country_codes  # base country; remote regions EU, UK
    assert checkpoint.scope.include_worldwide is True


async def test_stored_filters_override_the_defaults(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    seen: list[SourceCheckpoint] = []

    def provider(checkpoint: SourceCheckpoint) -> object:
        seen.append(checkpoint)
        return listing()

    source = await board(db_session)
    source.config_json = {"schema_version": 1, "max_age_days": 7, "search_terms": ["rust"]}
    await db_session.flush()
    await run(build(db_session, monkeypatch, FakeAdapter(provider=provider), clock), source)
    assert seen[0].filters is not None
    assert (seen[0].filters.max_age_days, seen[0].filters.search_terms) == (7, ["rust"])


async def test_without_an_enabled_intent_the_board_fails_before_any_request(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    await db_session.execute(update(SearchIntent).values(enabled=False))
    adapter = FakeAdapter(provider=lambda checkpoint: pytest.fail("no request expected"))
    source = await board(db_session)
    queued = await run(build(db_session, monkeypatch, adapter, clock), source)
    result = await last_result(db_session, source)
    assert result.outcome == SourceOutcome.FAILED.value
    assert result.error_class == SourceErrorClass.CONFIGURATION.value
    assert "Profile & intent" in (result.error_message or "")
    await db_session.refresh(queued)
    assert queued.status == RunStatus.FAILED.value


# --- dropped, truncated ---------------------------------------------------------------------------


async def test_the_number_of_dropped_postings_is_recorded(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    adapter = FakeAdapter([listing(make_posting("1", company_name="Acme Robotics"), dropped=7)])
    source = await board(db_session)
    await run(build(db_session, monkeypatch, adapter, clock), source)
    assert (await last_result(db_session, source)).dropped_count == 7


async def test_a_truncated_run_is_partial_and_a_board_never_closes_postings(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    a = make_posting("A", company_name="Acme Robotics")
    b = make_posting("B", company_name="Acme Robotics")
    adapter = FakeAdapter([listing(a, b), listing(a, truncated=True), listing(a), listing(a)])
    source = await board(db_session)
    service = build(db_session, monkeypatch, adapter, clock)

    await run(service, source)
    clock.advance(hours=7)
    second = await run(service, source)
    result = await last_result(db_session, source)
    assert result.outcome == SourceOutcome.PARTIAL.value
    assert result.closed_count == 0
    await db_session.refresh(second)
    assert second.status == RunStatus.PARTIAL.value

    # One complete run without B is not enough: a partial run does not count as a miss.
    clock.advance(hours=7)
    await run(service, source)
    assert {
        p.external_job_id for p in await postings_of(db_session, source) if p.closed_at is None
    } == {"A", "B"}
    clock.advance(hours=7)
    await run(service, source)
    # ADR-063: a board only reads the latest days, so absence never closes a posting.
    open_ids = {
        p.external_job_id for p in await postings_of(db_session, source) if p.closed_at is None
    }
    assert open_ids == {"A", "B"}


# --- minimum interval ---------------------------------------------------------------------------


async def test_a_manual_run_before_the_minimum_interval_is_refused_with_the_time_it_is_allowed(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    adapter = FakeAdapter([listing(make_posting("1", company_name="Acme Robotics")), listing()])
    source = await board(db_session)
    service = build(db_session, monkeypatch, adapter, clock)
    await run(service, source)
    clock.advance(minutes=30)
    with pytest.raises(ConflictError) as error:
        await service.request_run(
            LOCAL_OWNER_ID, source_configuration_id=source.source_configuration_id
        )
    assert error.value.details["reason"] == "too_soon"
    allowed = datetime.fromisoformat(str(error.value.details["next_run_allowed_at"]))
    assert allowed == T0 + timedelta(minutes=360)
    clock.advance(hours=6)
    await service.request_run(
        LOCAL_OWNER_ID, source_configuration_id=source.source_configuration_id
    )


async def test_an_all_sources_run_skips_a_board_that_ran_too_recently(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    adapter = FakeAdapter([listing(make_posting("1", company_name="Acme Robotics"))])
    source = await board(db_session)
    source.enabled = True
    await db_session.flush()
    service = build(db_session, monkeypatch, adapter, clock)
    await run(service, source)
    clock.advance(minutes=30)
    queued = await service.request_run(LOCAL_OWNER_ID)
    await service.execute_run(queued.collection_run_id)
    result = await last_result(db_session, source)
    assert result.outcome == SourceOutcome.SKIPPED.value
    assert "ran recently" in (result.error_message or "").lower()
    await db_session.refresh(queued)
    assert queued.status == RunStatus.SUCCEEDED.value  # skipping is not a failure
    assert len(adapter.checkpoints) == 1


async def test_the_source_list_shows_when_the_next_run_is_allowed(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    adapter = FakeAdapter([listing(make_posting("1", company_name="Acme Robotics"))])
    source = await board(db_session)
    await run(build(db_session, monkeypatch, adapter, clock), source)
    rows = await SourceService(db_session, {}).list_with_status(LOCAL_OWNER_ID)
    row = next(
        r for r in rows if r.source.source_configuration_id == source.source_configuration_id
    )
    assert row.next_run_allowed_at == T0 + timedelta(minutes=360)


# --- the key ----------------------------------------------------------------------------------------


def key_box() -> CredentialBox:
    from cryptography.fernet import Fernet
    from pydantic import SecretStr

    return CredentialBox(SecretStr(Fernet.generate_key().decode()))


async def keyed_board(
    session: AsyncSession, box: CredentialBox | None, key: str | None
) -> SourceConfiguration:
    entry = require_entry("itjobs_pt")
    source = SourceConfiguration(
        owner_id=LOCAL_OWNER_ID,
        company_id=None,
        source_type=SourceType.ITJOBS_PT.value,
        external_identifier=entry.catalogue_key,
        display_name=entry.display_name,
        url=entry.endpoint,
        config_json={},
        credential_ciphertext=box.encrypt(key) if box and key else None,
    )
    session.add(source)
    await session.flush()
    return source


def build_keyed(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    adapter: FakeAdapter,
    clock: Clock,
    box: CredentialBox | None,
) -> CollectionService:
    service = build(session, monkeypatch, adapter, clock)
    return CollectionService(
        service._session_factory,
        {SourceType.ITJOBS_PT: adapter},
        clock=clock,
        box=box,
    )


async def test_the_stored_key_is_decrypted_only_into_the_checkpoint(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    seen: list[SourceCheckpoint] = []

    def provider(checkpoint: SourceCheckpoint) -> object:
        seen.append(checkpoint)
        return listing(make_posting("1", company_name="Acme Robotics"))

    box = key_box()
    source = await keyed_board(db_session, box, "the-itjobs-key")
    await run(
        build_keyed(db_session, monkeypatch, FakeAdapter(provider=provider), clock, box), source
    )
    assert seen[0].credential == "the-itjobs-key"
    assert "the-itjobs-key" not in repr(seen[0])
    result = await last_result(db_session, source)
    assert result.outcome == SourceOutcome.SUCCESS.value
    assert "the-itjobs-key" not in str(result.error_message)


@pytest.mark.parametrize("problem", ["no_key", "no_box", "wrong_box"])
async def test_a_key_that_cannot_be_used_fails_the_board_before_any_request(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock, problem: str
) -> None:
    box = key_box()
    source = await keyed_board(db_session, box, None if problem == "no_key" else "the-itjobs-key")
    used_box = {"no_key": box, "no_box": None, "wrong_box": key_box()}[problem]
    adapter = FakeAdapter(provider=lambda checkpoint: pytest.fail("no request expected"))
    await run(build_keyed(db_session, monkeypatch, adapter, clock, used_box), source)
    result = await last_result(db_session, source)
    assert result.outcome == SourceOutcome.FAILED.value
    assert result.error_class == SourceErrorClass.CONFIGURATION.value
    assert "the-itjobs-key" not in str(result.error_message)


async def test_a_job_board_never_closes_a_posting_it_no_longer_sees(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    """ADR-063: a posting that left the few days a board reads is not closed for that."""
    a = make_posting("A", company_name="Acme Robotics")
    b = make_posting("B", company_name="Acme Robotics")
    adapter = FakeAdapter([listing(a, b), listing(a), listing(a), listing(a)])
    source = await board(db_session)
    service = build(db_session, monkeypatch, adapter, clock)
    for _ in range(4):
        await run(service, source)
        clock.advance(hours=7)
    assert (await last_result(db_session, source)).closed_count == 0
    assert all(p.closed_at is None for p in await postings_of(db_session, source))


# --- the pre-filter rules of the owner's packs (ADR-080, phase 5) ---------------------------------------


async def checkpoint_of_a_run(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> SourceCheckpoint:
    seen: list[SourceCheckpoint] = []

    def provider(checkpoint: SourceCheckpoint) -> object:
        seen.append(checkpoint)
        return listing()

    await run(
        build(session, monkeypatch, FakeAdapter(provider=provider), clock), await board(session)
    )
    return seen[0]


async def test_the_adapter_receives_the_areas_and_noise_of_the_owners_packs(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    checkpoint = await checkpoint_of_a_run(db_session, monkeypatch, clock)
    assert checkpoint.rules is not None
    assert [a.key for a in checkpoint.rules.areas] == [
        "software", "data", "devops", "security", "telecom"
    ]  # fmt: skip
    assert checkpoint.rules.categorise(["Backend Developer"]) == {"software"}
    assert checkpoint.rules.categorise(["Data Annotator"]) == frozenset()  # noise


async def test_a_trades_pack_gives_the_adapter_trades_areas(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    from jobs_radar.services.packs import PackService

    packs = PackService(db_session)
    await packs.set_active(LOCAL_OWNER_ID, "software_data_it", active=False)
    await packs.set_active(LOCAL_OWNER_ID, "construction_trades", active=True)
    checkpoint = await checkpoint_of_a_run(db_session, monkeypatch, clock)
    assert checkpoint.rules is not None
    assert checkpoint.rules.categorise(["Maintenance Electrician"]) == {"electrical"}
    assert checkpoint.rules.categorise(["Backend Developer"]) == frozenset()
    assert checkpoint.filters is not None and "electrical" in checkpoint.filters.categories


async def test_with_no_pack_on_nothing_is_filtered_by_area(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    from jobs_radar.services.packs import PackService

    await PackService(db_session).set_active(LOCAL_OWNER_ID, "software_data_it", active=False)
    checkpoint = await checkpoint_of_a_run(db_session, monkeypatch, clock)
    assert checkpoint.rules is not None and checkpoint.rules.areas == ()
    assert checkpoint.filters is not None and checkpoint.filters.categories == []

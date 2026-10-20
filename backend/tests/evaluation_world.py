"""A synthetic world for evaluation tests: one profile, one enabled intent, one extracted job."""

from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models import JobExtraction, JobPosting
from jobs_radar.domain.enums import LOCAL_OWNER_ID, SkillKind
from jobs_radar.schemas.extraction import ExtractedSkill
from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.schemas.profile_api import ProfileInput
from jobs_radar.services.intents import IntentService
from jobs_radar.services.profiles import ProfileService
from jobs_radar.services.skills import SkillCanonicaliser
from tests.data import (
    SAMPLE_JOB_DESCRIPTION,
    SAMPLE_JOB_TITLE,
    sample_extraction_output,
    sample_intent,
    sample_profile_input,
)
from tests.factories import make_company, make_posting, make_source, unique

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


class World:
    """One profile, one enabled intent and one extracted job, all synthetic."""

    def __init__(self) -> None:
        self.session: AsyncSession
        self.profile_id: int
        self.profile_revision_id: int
        self.intent_id: int
        self.intent_revision_id: int
        self.posting: JobPosting
        self.snapshot_id: int
        self.extraction_id: int
        self.held: str
        self.unheld: str
        self.credential_ids: list[int] = []
        self.credential_names: list[str] = []


async def world(
    session: AsyncSession,
    *,
    extracted_by: tuple[str, str] | None = None,
    with_extraction: bool = True,
    locations: list[str] | None = None,
    credentials: list[str] | None = None,
    schedule: list[str] | None = None,
    travel: str | None = None,
) -> World:
    """Build the world; ``extracted_by`` is the ``(provider, model)`` that extracted the job.

    ``locations`` are the board's own places for the job (the sample job's when omitted).
    ``schedule`` and ``travel`` are the working patterns and travel level the job states.
    ``credentials`` are licences or certifications the job requires (all ``must``), stored as the
    extraction would (ADR-080, phase 6a).
    """
    await session.execute(
        update(JobPosting).where(JobPosting.closed_at.is_(None)).values(closed_at=NOW)
    )
    w = World()
    w.session = session
    w.held, w.unheld = unique("Held Skill"), unique("Other Skill")

    profile_input = sample_profile_input()
    profile_input["skills"] = [
        {"name": w.held, "kind": "technology", "level": "expert", "years": 5}
    ]
    profiles = ProfileService(session)
    profile = await profiles.create(LOCAL_OWNER_ID, unique("Eval profile"))
    w.profile_id = profile.profile.career_profile_id
    saved = await profiles.save(
        LOCAL_OWNER_ID,
        w.profile_id,
        ProfileInput.model_validate(profile_input),
        expected_current_revision=None,
    )
    w.profile_revision_id = saved.view.revision.profile_revision_id

    intents = IntentService(session)
    created = await intents.create(
        LOCAL_OWNER_ID, w.profile_id, IntentDefinition.model_validate(sample_intent()), enabled=True
    )
    w.intent_id = created.intent.search_intent_id
    assert created.current is not None
    w.intent_revision_id = created.current.intent_revision_id

    source = await make_source(session, await make_company(session, "Acme Evaluation"))
    w.posting, snapshot = await make_posting(
        session,
        source,
        title=SAMPLE_JOB_TITLE,
        description=SAMPLE_JOB_DESCRIPTION,
        locations=locations,
    )
    w.snapshot_id = snapshot.job_snapshot_id
    resolved = await SkillCanonicaliser(session).canonicalise(
        [
            ExtractedSkill(name=w.held, importance="must", evidence=w.held),
            ExtractedSkill(name=w.unheld, importance="must", evidence=w.unheld),
        ]
    )
    if not with_extraction:
        return w
    required = [
        ExtractedSkill(name=name, importance="must", evidence="licence required")
        for name in credentials or []
    ]
    held_credentials = await SkillCanonicaliser(session).canonicalise(
        required, SkillKind.CREDENTIAL
    )
    w.credential_ids = [c.skill_id for c in held_credentials]
    w.credential_names = [c.name for c in held_credentials]
    output = sample_extraction_output()
    output["credentials"] = [r.model_dump() for r in required]
    if schedule:
        output["schedule"] = {
            "value": schedule,
            "status": "known",
            "confidence": 0.9,
            "evidence": "shift work",
        }
    if travel:
        output["travel"] = {
            "value": travel,
            "status": "known",
            "confidence": 0.9,
            "evidence": "travel",
        }
    extraction = JobExtraction(
        job_snapshot_id=w.snapshot_id,
        status="succeeded",
        provider=extracted_by[0] if extracted_by else "fixture",
        model=extracted_by[1] if extracted_by else unique("m"),
        prompt_version="extract-v2",
        taxonomy_version_id=1,
        attributes_json={
            "output": output,
            "unverified": [],
            "dropped_keys": [],
            "contradictions": [],
            "skills_resolved": [
                {"skill_id": r.skill_id, "name": r.name, "importance": r.importance}
                for r in resolved
            ],
            "credentials_resolved": [
                {"skill_id": c.skill_id, "name": c.name, "importance": c.importance}
                for c in held_credentials
            ],
            "locations_resolved": [{"raw": "Remote - EU", "resolved": False}],
        },
        attempts=1,
        completed_at=NOW,
    )
    session.add(extraction)
    await session.flush()
    w.extraction_id = extraction.job_extraction_id
    return w

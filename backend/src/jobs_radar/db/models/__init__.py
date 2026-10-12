"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from jobs_radar.db.models.audit import AuditEvent
from jobs_radar.db.models.company import (
    Company,
    CompanyAlias,
    CompanyEnrichmentCandidate,
    CompanyFact,
    CompanyFollow,
    CompanyIgnore,
)
from jobs_radar.db.models.evaluation import DirectionJudgement, MatchEvaluation, ScoreDimension
from jobs_radar.db.models.inbox import InboxEvent, JobInboxItem
from jobs_radar.db.models.intent import IntentRevision, SearchIntent
from jobs_radar.db.models.job import (
    JobChangeEvent,
    JobExtraction,
    JobOpportunity,
    JobOpportunityLink,
    JobPosting,
    JobSnapshot,
    JobSummary,
)
from jobs_radar.db.models.owner import Owner
from jobs_radar.db.models.profile import (
    CareerProfile,
    Document,
    Evidence,
    ProfileProposal,
    ProfileRevision,
    ProposalItem,
)
from jobs_radar.db.models.provider import IntegrationCredential, PrivacySetting, ProviderConnection
from jobs_radar.db.models.skills import Skill, SkillAlias, SkillCandidate, SkillRelation
from jobs_radar.db.models.source import (
    CollectionRun,
    ScheduleSetting,
    SourceConfiguration,
    SourceRunResult,
)
from jobs_radar.db.models.taxonomy import TaxonomyTerm, TaxonomyVersion
from jobs_radar.db.models.trend import TrendWeekly
from jobs_radar.db.models.worker import WorkerHeartbeat

__all__ = [
    "AuditEvent",
    "CareerProfile",
    "CollectionRun",
    "Company",
    "CompanyAlias",
    "CompanyEnrichmentCandidate",
    "CompanyFact",
    "CompanyFollow",
    "CompanyIgnore",
    "DirectionJudgement",
    "Document",
    "Evidence",
    "InboxEvent",
    "IntegrationCredential",
    "IntentRevision",
    "JobChangeEvent",
    "JobExtraction",
    "JobInboxItem",
    "JobOpportunity",
    "JobOpportunityLink",
    "JobPosting",
    "JobSnapshot",
    "JobSummary",
    "MatchEvaluation",
    "Owner",
    "PrivacySetting",
    "ProfileProposal",
    "ProfileRevision",
    "ProposalItem",
    "ProviderConnection",
    "ScheduleSetting",
    "ScoreDimension",
    "SearchIntent",
    "Skill",
    "SkillAlias",
    "SkillCandidate",
    "SkillRelation",
    "SourceConfiguration",
    "SourceRunResult",
    "TaxonomyTerm",
    "TaxonomyVersion",
    "TrendWeekly",
    "WorkerHeartbeat",
]

"""Enumerations shared by the whole application (documents 06 and 13).

They are plain ``StrEnum`` values so they serialise to the exact strings stored in the database
and exposed by the API. This module imports nothing from the rest of the application.
"""

from datetime import UTC, datetime
from enum import StrEnum


class TaxonomyKind(StrEnum):
    """Kind of controlled-vocabulary term (document 13, section 2)."""

    ROLE_FAMILY = "role_family"
    SECTOR = "sector"
    SENIORITY_LEVEL = "seniority_level"
    ENGAGEMENT_TYPE = "engagement_type"
    WORK_ARRANGEMENT = "work_arrangement"
    EMPLOYER_TYPE = "employer_type"
    BENEFIT = "benefit"


class TermOrigin(StrEnum):
    """Where a taxonomy term came from."""

    SEED = "seed"
    USER = "user"
    AI_PROPOSAL_ACCEPTED = "ai_proposal_accepted"


class SkillKind(StrEnum):
    """Category of a skill."""

    TECHNOLOGY = "technology"
    DOMAIN_KNOWLEDGE = "domain_knowledge"
    METHOD = "method"


class SkillRelationKind(StrEnum):
    """Judged relation between two skills."""

    EQUIVALENT = "equivalent"
    RELATED = "related"
    UNRELATED = "unrelated"


class JudgementOrigin(StrEnum):
    """Who produced a judgement."""

    AI = "ai"
    USER = "user"


class CandidateStatus(StrEnum):
    """Review state of a proposed new skill."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class EvidenceOrigin(StrEnum):
    """Origin of a profile fact's evidence."""

    DOCUMENT = "document"
    LLM = "llm"
    MANUAL = "manual"
    IMPORT = "import"


class DocumentExtractionStatus(StrEnum):
    """Text-extraction state of an uploaded document."""

    UPLOADED = "uploaded"
    EXTRACTED = "extracted"
    NEEDS_OCR = "needs_ocr"
    FAILED = "failed"


class ProposalStatus(StrEnum):
    """State of a profile proposal."""

    PENDING = "pending"
    COMPLETED = "completed"


class ProposalItemStatus(StrEnum):
    """Review decision for one proposed profile item."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class Visibility(StrEnum):
    """Visibility of a career profile."""

    PRIVATE = "private"


class Stance(StrEnum):
    """The owner's attitude to an option (ADR-026)."""

    PREFERRED = "preferred"
    ACCEPTABLE = "acceptable"
    REJECTED = "rejected"


class DirectionLevel(StrEnum):
    """How well a job fits one career direction, as judged by the local model (ADR-057)."""

    STRONG = "strong"
    PARTIAL = "partial"
    WEAK = "weak"
    NONE = "none"
    UNKNOWN = "unknown"


class SummaryStatus(StrEnum):
    """Outcome of one job-summary attempt that was stored (ADR-059)."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SourceType(StrEnum):
    """Kind of job source adapter: ATS company boards first, then job boards (ADR-049)."""

    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    SMARTRECRUITERS = "smartrecruiters"
    EIGHTFOLD = "eightfold"
    ARBEITNOW = "arbeitnow"
    JOBICY = "jobicy"
    HIMALAYAS = "himalayas"
    ITJOBS_PT = "itjobs_pt"


class SourceCategory(StrEnum):
    """Whether a source is one company's board or a board with the postings of many companies."""

    COMPANY_BOARD = "company_board"
    JOB_BOARD = "job_board"


class RunTrigger(StrEnum):
    """What started a collection run."""

    SCHEDULED = "scheduled"
    MANUAL = "manual"


class RunStatus(StrEnum):
    """State of a collection run."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SourceOutcome(StrEnum):
    """Result of collecting one source within a run."""

    SUCCESS = "success"
    NOT_MODIFIED = "not_modified"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class SourceErrorClass(StrEnum):
    """Stable, machine-readable reason why collecting a source failed."""

    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    INVALID_PAYLOAD = "invalid_payload"
    NETWORK_ERROR = "network_error"
    TOO_LARGE = "too_large"
    BLOCKED_URL = "blocked_url"
    HTTP_ERROR = "http_error"
    CONFIGURATION = "configuration"
    AUTHENTICATION = "authentication"
    UNKNOWN = "unknown"


class ProviderErrorClass(StrEnum):
    """Stable, machine-readable reason why an AI provider call failed."""

    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    MODEL_NOT_FOUND = "model_not_found"
    INVALID_RESPONSE = "invalid_response"
    BLOCKED_URL = "blocked_url"
    HTTP_ERROR = "http_error"
    UNAUTHORIZED = "unauthorized"
    RATE_LIMITED = "rate_limited"


class JobExtractionStatus(StrEnum):
    """State of an AI extraction for a job snapshot."""

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LinkState(StrEnum):
    """State of a link between a posting and an opportunity (ADR-023)."""

    AUTO = "auto"
    POSSIBLE = "possible"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class Recommendation(StrEnum):
    """Evaluation outcome after the hard gates."""

    RECOMMENDED = "recommended"
    NOT_RECOMMENDED = "not_recommended"


class ScoreStatus(StrEnum):
    """Status of one score dimension."""

    MATCH = "match"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


class MatchQuality(StrEnum):
    """Derived label for a matching dimension (document 13, section 7.3)."""

    STRONG = "strong"
    PARTIAL = "partial"
    WEAK = "weak"


class InboxState(StrEnum):
    """State of a job inbox item (LLD section 3)."""

    UNREAD = "unread"
    READ = "read"
    UPDATED_UNREAD = "updated_unread"
    IGNORED = "ignored"
    ARCHIVED = "archived"
    APPLIED = "applied"


class InboxAction(StrEnum):
    """Action recorded in the inbox event stream."""

    SURFACE_NEW = "surface_new"
    OPEN = "open"
    MARK_UNREAD = "mark_unread"
    SHORTLIST = "shortlist"
    UNSHORTLIST = "unshortlist"
    IGNORE = "ignore"
    RESTORE = "restore"
    ARCHIVE = "archive"
    RECORD_APPLICATION = "record_application"
    MATERIAL_UPDATE = "material_update"


class Actor(StrEnum):
    """Who performed an action."""

    USER = "user"
    SYSTEM = "system"


class ProviderType(StrEnum):
    """Kind of AI provider connection."""

    OLLAMA = "ollama"
    OPENAI = "openai"
    MINIMAX = "minimax"
    COMPATIBLE = "compatible"


class EmployerType(StrEnum):
    """Kind of employer (document 13, section 2.1)."""

    DIRECT_EMPLOYER = "direct_employer"
    AGENCY_RECRUITER = "agency_recruiter"
    CONSULTANCY_OUTSOURCER = "consultancy_outsourcer"


class EmployerTypeOrigin(StrEnum):
    """Where an employer-type classification came from."""

    SOURCE = "source"
    AI_INFERENCE = "ai_inference"
    USER = "user"


class EnrichmentCandidateStatus(StrEnum):
    """State of an enrichment candidate (an entity that may be the company)."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class FactOrigin(StrEnum):
    """Origin of a company fact."""

    SOURCE = "source"
    PUBLIC_DATASET = "public_dataset"
    AI_INFERENCE = "ai_inference"
    USER = "user"


class TrendTermKind(StrEnum):
    """Kind of term aggregated by the weekly trends job."""

    SKILL = "skill"
    ROLE_FAMILY = "role_family"
    SECTOR = "sector"
    WORK_ARRANGEMENT = "work_arrangement"
    SENIORITY_LEVEL = "seniority_level"
    ENGAGEMENT_TYPE = "engagement_type"


# Policy versions stored with the results they produced.
MATCHING_POLICY_VERSION = "matching-v1"
DEDUP_POLICY_VERSION = "dedup-v1"
EXTRACTION_PROMPT_VERSION = "extract-v2"
DIRECTION_PROMPT_VERSION = "direction-v1"
SUMMARY_PROMPT_VERSION = "summary-v1"
# The worker writes summaries only for jobs first seen on or after this moment (ADR-059): the jobs
# collected and analysed before the feature are summarised on demand or by the sample tool.
SUMMARIES_FROM = datetime(2026, 10, 11, 15, 0, tzinfo=UTC)

# The single owner of V1: there is no authentication (ADR-009), but ``owner_id`` is kept everywhere.
LOCAL_OWNER_ID = 1

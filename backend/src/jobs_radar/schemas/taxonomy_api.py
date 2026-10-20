"""API contracts for editing the vocabulary (ADR-080, phase 3)."""

from typing import Annotated

from pydantic import StringConstraints

from jobs_radar.schemas.common import StrictModel

TermLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class TaxonomyTermCreate(StrictModel):
    """A term the owner adds; the key is derived from the label and never changes."""

    kind: str
    label: TermLabel


class TaxonomyTermUpdate(StrictModel):
    """A change to a term: a new label, or switching it off and on. At least one is required."""

    label: TermLabel | None = None
    active: bool | None = None


class TaxonomyTermAdmin(StrictModel):
    """A term with its state, for the screen where the owner manages the vocabulary."""

    kind: str
    term_key: str
    label: str
    origin: str
    active: bool
    introduced_in_taxonomy_version_id: int


class TaxonomyTermList(StrictModel):
    """Every term of the editable vocabularies, active or not."""

    taxonomy_version_id: int
    terms: list[TaxonomyTermAdmin]


class TaxonomyTermMerge(StrictModel):
    """The term that takes over the merged one."""

    into: str


class MergeImpactRead(StrictModel):
    """One search intent that mentions the term being merged."""

    search_intent_id: int
    title: str
    from_stance: str
    into_stance: str | None
    conflict: bool


class MergePreviewRead(StrictModel):
    """The searches a merge would touch, so the owner can see conflicts before confirming."""

    intents: list[MergeImpactRead]

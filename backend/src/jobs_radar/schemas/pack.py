"""The format of a domain pack file (ADR-080).

A pack is plain data, validated when it is loaded. Unknown fields are rejected, so a pack written
for a later version of Jobs Radar fails loudly instead of being half understood.
"""

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from jobs_radar.schemas.common import StrictModel, TaxonomyKey
from jobs_radar.schemas.taxonomy_api import TermLabel

PackKey = Annotated[
    str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", min_length=3, max_length=60)
]

# Kept out of every pack: it is always offered, whichever packs are on.
_RESERVED_KEYS = frozenset({"other"})


class PackTerm(StrictModel):
    """A role family or a sector a pack lists."""

    key: TaxonomyKey
    label: TermLabel


def _check_terms(terms: list[PackTerm], what: str) -> None:
    keys = [term.key for term in terms]
    labels = [term.label.casefold() for term in terms]
    if len(set(keys)) != len(keys):
        msg = f"{what}: a key is listed twice"
        raise ValueError(msg)
    if len(set(labels)) != len(labels):
        msg = f"{what}: a label is used twice"
        raise ValueError(msg)
    if reserved := sorted(_RESERVED_KEYS & set(keys)):
        msg = f"{what}: {', '.join(reserved)} belongs to no pack and cannot be listed"
        raise ValueError(msg)


class PackFile(StrictModel):
    """One domain pack: the role families and sectors of a field of work."""

    schema_version: Literal[1] = 1
    key: PackKey
    version: int = 1
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
    ]
    role_families: list[PackTerm]
    sectors: list[PackTerm] = Field(default_factory=list)

    @model_validator(mode="after")
    def _terms_are_sound(self) -> Self:
        if self.version < 1:
            msg = "version starts at 1"
            raise ValueError(msg)
        if not self.role_families:
            msg = "a pack needs at least one role family"
            raise ValueError(msg)
        _check_terms(self.role_families, "role_families")
        _check_terms(self.sectors, "sectors")
        return self

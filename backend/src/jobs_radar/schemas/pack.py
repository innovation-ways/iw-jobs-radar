"""The format of a domain pack file (ADR-080).

A pack is plain data, validated when it is loaded. Unknown fields are rejected, so a pack written
for a later version of Jobs Radar fails loudly instead of being half understood.
"""

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from jobs_radar.domain.prefilter import Area, PrefilterRules
from jobs_radar.domain.skills import normalise_skill_name
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


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class PackCredential(StrictModel):
    """A licence or certification people in the field hold and jobs ask for (ADR-080).

    The name becomes a canonical skill of kind ``credential``; the aliases are other ways it is
    written in postings and CVs ("category B licence"), so a mention resolves to the same skill.
    """

    name: Name
    aliases: list[Name] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _names_can_be_matched(self) -> Self:
        for text in (self.name, *self.aliases):
            if not normalise_skill_name(text):
                msg = f"credential {self.name!r}: {text!r} has no letter or digit to match on"
                raise ValueError(msg)
        return self


class PackArea(StrictModel):
    """An area of work for the job-board pre-filter, with the keywords that put a posting in it."""

    key: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=40)]
    label: TermLabel
    keywords: Annotated[list[str], Field(min_length=1, max_length=80)]

    @model_validator(mode="after")
    def _keywords_are_plain(self) -> Self:
        Area(self.key, self.label, tuple(self.keywords))  # raises ValueError on a bad keyword
        return self


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
    # Job-board pre-filter (ADR-080, phase 5): areas of work with keywords, and words that rule a
    # posting out. Keywords are plain text, see ``jobs_radar.domain.prefilter``.
    areas: list[PackArea] = Field(default_factory=list)
    noise: Annotated[list[str], Field(max_length=80)] = Field(default_factory=list)
    # Licences and certifications of the field (ADR-080, phase 6a).
    credentials: list[PackCredential] = Field(default_factory=list, max_length=60)

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
        keys = [area.key for area in self.areas]
        labels = [area.label.casefold() for area in self.areas]
        if len(set(keys)) != len(keys) or len(set(labels)) != len(labels):
            msg = "areas: a key or a label is used twice"
            raise ValueError(msg)
        names = [normalise_skill_name(c.name) for c in self.credentials]
        if len(set(names)) != len(names):
            msg = "credentials: a name is used twice"
            raise ValueError(msg)
        PrefilterRules((), tuple(self.noise))  # raises ValueError on a bad noise keyword
        return self

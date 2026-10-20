"""Read and edit the controlled vocabularies (ADR-080, phase 3).

The owner can add role families and sectors, relabel any of their terms and switch terms off and on.
Nothing is deleted and keys never change, so stored intents, extractions and evaluations stay valid.
Every real change records a new taxonomy version.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import ConflictError, InputValidationError, NotFoundError
from jobs_radar.db.models import TaxonomyTerm
from jobs_radar.domain.enums import TermOrigin
from jobs_radar.domain.taxonomy_terms import EDITABLE_KINDS, term_key_from_label
from jobs_radar.repositories.taxonomy import TaxonomyRepository

_MAX_LABEL = 120


class TaxonomyService:
    """Lists the terms grouped by kind and applies the owner's edits. The caller commits."""

    def __init__(self, session: AsyncSession) -> None:
        self._taxonomy = TaxonomyRepository(session)

    async def groups(self, *, include_inactive: bool = False) -> dict[str, list[TaxonomyTerm]]:
        """Return the current terms of each kind, ordered by label (active ones unless asked)."""
        grouped: dict[str, list[TaxonomyTerm]] = {}
        for term in await self._taxonomy.terms(include_inactive=include_inactive):
            grouped.setdefault(term.kind, []).append(term)
        return grouped

    async def editable_terms(self) -> list[TaxonomyTerm]:
        """Return every term of the editable vocabularies, active or not."""
        return [
            term
            for term in await self._taxonomy.terms(include_inactive=True)
            if term.kind in EDITABLE_KINDS
        ]

    async def current_version_id(self) -> int:
        """Return the current taxonomy version."""
        return await self._taxonomy.current_version_id()

    @staticmethod
    def _editable(kind: str) -> None:
        if kind not in EDITABLE_KINDS:
            msg = f"The {kind} vocabulary cannot be edited; only {', '.join(EDITABLE_KINDS)} can."
            raise InputValidationError(msg, details={"editable_kinds": list(EDITABLE_KINDS)})

    @staticmethod
    def _clean(label: str) -> str:
        label = " ".join(label.split())
        if not label or len(label) > _MAX_LABEL:
            msg = f"The label must have 1 to {_MAX_LABEL} characters."
            raise InputValidationError(msg)
        return label

    async def _check_label_is_free(self, kind: str, label: str, *, own: str | None = None) -> None:
        taken = {existing.casefold() for existing in await self._taxonomy.labels_of_kind(kind)}
        if own is not None:
            taken.discard(own.casefold())
        if label.casefold() in taken:
            msg = f"There is already a {kind} called '{label}'."
            raise ConflictError(msg)

    async def add(self, kind: str, label: str) -> TaxonomyTerm:
        """Add a term the owner wrote; returns it with a key derived from the label."""
        self._editable(kind)
        label = self._clean(label)
        try:
            key = term_key_from_label(label)
        except ValueError as error:
            raise InputValidationError(str(error)) from error
        await self._check_label_is_free(kind, label)
        if await self._taxonomy.find(kind, key) is not None:
            msg = f"A {kind} with the key '{key}' already exists; use another label."
            raise ConflictError(msg)
        version_id = await self._taxonomy.new_version(f"added {kind} '{key}'")
        return await self._taxonomy.add(
            kind=kind,
            term_key=key,
            label=label,
            origin=TermOrigin.USER.value,
            version_id=version_id,
        )

    async def update(
        self,
        kind: str,
        term_key: str,
        *,
        label: str | None = None,
        active: bool | None = None,
    ) -> TaxonomyTerm:
        """Relabel a term or switch it off or on. A change that changes nothing records nothing."""
        self._editable(kind)
        if label is None and active is None:
            msg = "Give a new label, an active state, or both."
            raise InputValidationError(msg)
        term = await self._taxonomy.find(kind, term_key)
        if term is None or term.replaced_by_taxonomy_term_id is not None:
            msg = f"There is no {kind} '{term_key}'."
            raise NotFoundError(msg)
        changes: list[str] = []
        if label is not None:
            label = self._clean(label)
            if label != term.label:
                await self._check_label_is_free(kind, label, own=term.label)
                term.label = label
                changes.append("relabelled")
        if active is not None and active != term.is_active:
            term.is_active = active
            changes.append("switched on" if active else "switched off")
        if changes:
            await self._taxonomy.new_version(f"{kind} '{term_key}' {' and '.join(changes)}")
        return term

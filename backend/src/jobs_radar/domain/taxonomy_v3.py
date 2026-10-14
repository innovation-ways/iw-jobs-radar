"""Taxonomy v3 additions: the agency contract engagement type (ADR-073).

FROZEN: this is what migration 0025 inserted. Never edit it to change the live taxonomy; add a new
migration that inserts or merges terms and bumps the taxonomy version instead.
"""

# Version 1 had a term for an own-company contractor (``contractor_b2b``) and for a freelancer, but
# none for the common case of a contract placed through an agency or umbrella company, so those
# postings were forced into one of the other two.
TAXONOMY_V3_ADDITIONS: dict[str, tuple[str, ...]] = {
    "engagement_type": ("contractor_agency",),
}

V3_LABELS: dict[str, str] = {
    "contractor_agency": "Contract via agency",
}

V3_DESCRIPTION = "agency contract engagement type (ADR-073)"

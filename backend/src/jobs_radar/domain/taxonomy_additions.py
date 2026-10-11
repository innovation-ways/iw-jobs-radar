"""Taxonomy v2 additions: role families for non-technical work (ADR-060).

FROZEN: this is what migration 0017 inserted. Never edit it to change the live taxonomy; add a new
migration that inserts or merges terms and bumps the taxonomy version instead.
"""

# Version 1 had no family for finance, legal, HR and similar work, so the model returned no family
# for those postings and gate G1 could not fire. With these terms the model can classify them and
# the owner can reject them in the Search Intent.
TAXONOMY_V2_ADDITIONS: dict[str, tuple[str, ...]] = {
    "role_family": (
        "finance_accounting",
        "legal_compliance",
        "hr_recruiting",
        "marketing_communications",
        "operations_admin",
        "design_creative",
    ),
}

V2_LABELS: dict[str, str] = {
    "finance_accounting": "Finance and accounting",
    "legal_compliance": "Legal and compliance",
    "hr_recruiting": "HR and recruiting",
    "marketing_communications": "Marketing and communications",
    "operations_admin": "Operations and administration",
    "design_creative": "Design and creative",
}

V2_DESCRIPTION = "non-technical role families (ADR-060)"

"""Taxonomy v4 additions: working patterns and travel (ADR-080, phase 6b).

FROZEN: this is what migration 0032 inserted. Never edit it to change the live taxonomy; add a new
migration that inserts or merges terms and bumps the taxonomy version instead.
"""

# Two vocabularies that are options of the scoring model itself, like work arrangement: they do not
# belong to any domain pack. Shift work, weekends and on-call duty matter to a nurse or a plumber
# as much as remote work matters to a developer; so does how much of the job is travelling.
TAXONOMY_V4_ADDITIONS: dict[str, tuple[str, ...]] = {
    "schedule": ("day", "night", "rotating_shifts", "weekends", "on_call"),
    "travel_level": ("none", "occasional", "frequent"),
}

V4_LABELS: dict[str, str] = {
    "day": "Day work",
    "night": "Night work",
    "rotating_shifts": "Rotating shifts",
    "weekends": "Weekend work",
    "on_call": "On call",
    "none": "No travel",
    "occasional": "Occasional travel",
    "frequent": "Frequent travel",
}

V4_DESCRIPTION = "schedule and travel vocabularies (ADR-080)"

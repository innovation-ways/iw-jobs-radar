"""Describes the owner's profile for the pre-application prompt (ADR-064).

A pure function (no I/O): it turns the stored facts into plain text for the model and into the
set of words an evidence line may rest on (skill names, employers, titles, studies,
certifications), so the writer can drop a strength the profile does not support. No contact
details exist in the facts, and none are added.
"""

from dataclasses import dataclass

from jobs_radar.domain.text_match import normalise_for_match
from jobs_radar.schemas.profile import ProfileFacts


@dataclass(frozen=True)
class ProfileDigest:
    """The profile as prompt text, plus the normalised terms that count as evidence."""

    text: str
    vocabulary: frozenset[str]


def describe_profile(facts: ProfileFacts, skill_names: dict[int, str]) -> ProfileDigest:
    """Return the digest of one profile revision.

    ``skill_names`` maps the skill ids of the facts to their canonical names; an unknown id is
    left out rather than guessed.
    """
    lines = [
        f"Headline: {facts.headline}",
        f"Years of experience: {facts.years_experience}",
        f"Based in: {facts.base_location.place} ({facts.base_location.country})",
    ]
    terms: list[str] = []
    if facts.languages:
        lines.append(
            "Languages: " + ", ".join(f"{x.language} ({x.level})" for x in facts.languages)
        )
    skills = [(skill_names[s.skill_id], s) for s in facts.skills if s.skill_id in skill_names]
    if skills:
        lines.append("Skills:")
        for name, skill in skills:
            lines.append(f"- {name}: {skill.level}, {skill.years:g} years")
            terms.append(name)
    if facts.experience:
        lines.append("Experience:")
        for job in facts.experience:
            period = f"{job.start} to {job.end or 'present'}"
            lines.append(f"- {job.title} at {job.organisation} ({period})")
            if job.summary:
                lines.append(f"  {job.summary}")
            terms += [job.title, job.organisation]
    if facts.education:
        lines.append("Education:")
        for item in facts.education:
            lines.append(f"- {item.level} in {item.field}")
            terms.append(item.field)
    if facts.certifications:
        lines.append("Certifications:")
        for cert in facts.certifications:
            lines.append(f"- {cert.name}")
            terms.append(cert.name)
    vocabulary = frozenset(t for t in (normalise_for_match(term) for term in terms) if t)
    return ProfileDigest("\n".join(lines), vocabulary)

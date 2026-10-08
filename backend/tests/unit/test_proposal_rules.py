"""Turning a model's answer into reviewable proposal items (T6.5): salvage, validation, excerpts."""

import json

from jobs_radar.services.proposal_rules import parse_draft

CV = (
    "Alex Example. Senior Software Engineer with 9 years of experience. "
    "Northwind Labs, Staff Engineer, 2019-03 to 2023-11: built Python and PostgreSQL services. "
    "Skills: Python (expert, 8 years), Docker. Languages: English (C1), Portuguese (native). "
    "Lives in Lisbon, Portugal. MSc Computer Science. AWS Certified Developer 2021."
)


def answer(*items: dict) -> str:  # type: ignore[type-arg]
    return json.dumps({"items": list(items)})


def item(path: str, value: object, excerpt: str | None = None, confidence: float = 0.9) -> dict:  # type: ignore[type-arg]
    return {"path": path, "value": value, "excerpt": excerpt, "confidence": confidence}


def test_valid_items_of_every_kind_are_kept_with_verified_excerpts() -> None:
    result = parse_draft(
        answer(
            item("headline", "Senior Software Engineer", "Senior Software Engineer"),
            item("years_experience", 9, "9 years of experience"),
            item("base_location", {"place": "Lisbon", "country": "PT"}, "Lisbon, Portugal"),
            item("languages", {"language": "en", "level": "C1"}, "English (C1)"),
            item(
                "skills",
                {"name": "Python", "level": "expert", "years": 8},
                "Python (expert, 8 years)",
            ),
            item(
                "experience",
                {
                    "title": "Staff Engineer",
                    "organisation": "Northwind Labs",
                    "start": "2019-03",
                    "end": "2023-11",
                },
                "Northwind Labs, Staff Engineer, 2019-03 to 2023-11",
            ),
            item(
                "education", {"level": "MSc", "field": "Computer Science"}, "MSc Computer Science"
            ),
            item(
                "certifications",
                {"name": "AWS Certified Developer", "year": 2021},
                "AWS Certified Developer 2021",
            ),
        ),
        CV,
    )
    assert [i.path for i in result.items] == [
        "headline",
        "years_experience",
        "base_location",
        "languages",
        "skills",
        "experience",
        "education",
        "certifications",
    ]
    assert result.dropped == 0 and all(i.excerpt for i in result.items)
    assert result.items[4].value == {
        "name": "Python",
        "kind": "technology",
        "level": "expert",
        "years": 8.0,
    }


def test_an_excerpt_that_is_not_in_the_text_is_removed_not_trusted() -> None:
    result = parse_draft(answer(item("headline", "Senior Software Engineer", "invented quote")), CV)
    assert result.items[0].excerpt is None and result.items[0].confidence <= 0.5


def test_invalid_items_are_dropped_and_counted() -> None:
    result = parse_draft(
        answer(
            item("skills", {"name": "Go", "level": "godlike", "years": 3}),  # bad level
            item(
                "experience", {"title": "X", "organisation": "Y", "start": "2020-13"}
            ),  # bad month
            item("unknown_path", "x"),
            item("years_experience", 200),
            {"value": "no path"},
            "not even an object",
            item("headline", "Senior Software Engineer"),
        ),
        CV,
    )
    assert [i.path for i in result.items] == ["headline"] and result.dropped == 6


def test_only_the_most_confident_value_of_a_single_valued_path_is_kept() -> None:
    result = parse_draft(
        answer(
            item("headline", "Engineer", "Software Engineer", confidence=0.4),
            item(
                "headline", "Senior Software Engineer", "Senior Software Engineer", confidence=0.9
            ),
        ),
        CV,
    )
    assert [i.value for i in result.items] == ["Senior Software Engineer"]


def test_duplicate_skills_are_merged_by_name() -> None:
    result = parse_draft(
        answer(
            item(
                "skills",
                {"name": "Python", "level": "advanced", "years": 5},
                "Python",
                confidence=0.5,
            ),
            item(
                "skills",
                {"name": "python", "level": "expert", "years": 8},
                "Python",
                confidence=0.9,
            ),
        ),
        CV,
    )
    assert len(result.items) == 1 and result.items[0].value["years"] == 8.0  # type: ignore[index]


def test_a_confidence_outside_the_range_is_clamped_and_text_is_trimmed() -> None:
    result = parse_draft(
        answer(
            item(
                "headline", "  Senior Software Engineer  ", "Senior Software Engineer", confidence=7
            )
        ),
        CV,
    )
    assert result.items[0].confidence == 1.0 and result.items[0].value == "Senior Software Engineer"


def test_long_excerpts_are_shortened() -> None:
    text = "word " * 400
    result = parse_draft(answer(item("headline", "Engineer", text.strip())), text)
    assert result.items[0].excerpt is not None and len(result.items[0].excerpt) <= 300


def test_an_answer_that_is_not_json_has_no_items() -> None:
    assert parse_draft("sorry, I cannot do that", CV).items == []
    assert parse_draft('{"items": "oops"}', CV).items == []
    assert parse_draft("[]", CV).items == []


def test_fenced_json_is_accepted() -> None:
    fenced = "```json\n" + answer(item("headline", "Senior Software Engineer")) + "\n```"
    assert len(parse_draft(fenced, CV).items) == 1

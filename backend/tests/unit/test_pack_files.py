"""The packs that ship with the application (ADR-080)."""

from collections import defaultdict
from importlib import resources
from pathlib import Path

from tests.golden import load_golden

from jobs_radar.services.packs import shipped_packs

ROOT = Path(__file__).resolve().parents[3]
KINDS = (("role_family", "role_families"), ("sector", "sectors"))


def test_the_ten_packs_ship_as_package_data() -> None:
    files = sorted(
        e.name for e in resources.files("jobs_radar.packs").iterdir() if e.name.endswith(".json")
    )
    assert len(files) == 10
    assert [
        pack.key + ".json" for pack in shipped_packs()
    ] == files  # one file per pack, named by key


def test_the_backend_image_carries_the_packs() -> None:
    """The release images build from ``src`` and the wheel takes the whole package (ADR-079)."""
    assert "COPY src ./src" in (ROOT / "backend/Dockerfile").read_text()
    assert 'packages = ["src/jobs_radar"]' in (ROOT / "backend/pyproject.toml").read_text()


def test_every_pack_is_substantial_enough_to_start_with() -> None:
    """The owner should never have to add a term to begin (ADR-080)."""
    for pack in shipped_packs():
        assert len(pack.role_families) >= 10, pack.key
        assert len(pack.sectors) >= 5, pack.key
        assert pack.version >= 1 and pack.description.endswith("."), pack.key


def test_a_key_has_one_label_in_every_pack() -> None:
    labels: dict[tuple[str, str], set[str]] = defaultdict(set)
    for pack in shipped_packs():
        for kind, attribute in KINDS:
            for term in getattr(pack, attribute):
                labels[(kind, term.key)].add(term.label)
    assert {key: found for key, found in labels.items() if len(found) > 1} == {}


def test_the_software_pack_is_exactly_the_vocabulary_that_exists_today() -> None:
    """Phase 4: nothing the owner has is lost, and nothing else is in the software pack."""
    today: dict[str, dict[str, str]] = defaultdict(dict)
    for _id, kind, key, label, *_rest in load_golden("taxonomy_after_migrations")["terms"]:
        if kind in ("role_family", "sector") and key != "other":
            today[kind][key] = label
    (software,) = [pack for pack in shipped_packs() if pack.key == "software_data_it"]
    assert {t.key: t.label for t in software.role_families} == today["role_family"]
    assert {t.key: t.label for t in software.sectors} == today["sector"]


def test_other_packs_reuse_existing_terms_with_the_same_label() -> None:
    """A key that exists today keeps its label, so no pack renames what the owner already sees."""
    existing = {
        (kind, key): label
        for _id, kind, key, label, *_rest in load_golden("taxonomy_after_migrations")["terms"]
    }
    for pack in shipped_packs():
        for kind, attribute in KINDS:
            for term in getattr(pack, attribute):
                if (kind, term.key) in existing:
                    assert existing[(kind, term.key)] == term.label, (pack.key, term.key)

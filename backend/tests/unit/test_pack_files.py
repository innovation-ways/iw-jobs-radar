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


# --- areas and noise of each pack (ADR-080, phase 5) -------------------------------------------------


def test_every_pack_has_areas_with_enough_keywords() -> None:
    for pack in shipped_packs():
        assert len(pack.areas) >= 4, pack.key
        for area in pack.areas:
            assert len(area.keywords) >= 4, (pack.key, area.key)
        assert pack.noise, pack.key


def test_an_area_key_has_one_label_in_every_pack() -> None:
    labels: dict[str, set[str]] = defaultdict(set)
    for pack in shipped_packs():
        for area in pack.areas:
            labels[area.key].add(area.label)
    assert {key: found for key, found in labels.items() if len(found) > 1} == {}


# Titles a person in each field would expect the pre-filter to recognise (area keys of that pack).
EXPECTED = {
    "construction_trades": {
        "Maintenance Electrician": {"electrical"},
        "Plumber / Gas Engineer": {"plumbing_heating"},
        "HVAC Technician": {"hvac"},
        "Carpenter and Joiner": {"carpentry_building"},
        "Welder Fabricator": {"welding_metalwork"},
        "Site Supervisor": {"site_civil"},
    },
    "maintenance_repair": {
        "Maintenance Technician": {"maintenance"},
        "Automotive Mechanic": {"automotive_repair"},
        "Field Service Engineer": {"field_service"},
        "Fibre Installer": {"telecom_installation"},
    },
    "manufacturing_production": {
        "Production Operator": {"production"},
        "CNC Machinist": {"machining"},
        "Quality Inspector": {"quality"},
        "Food Production Operative": {"food_production"},
    },
    "logistics_transport": {
        "HGV Driver": {"driving"},
        "Warehouse Operative": {"warehouse"},
        "Parcel Courier": {"courier_delivery"},
        "Transport Planner": {"logistics_planning"},
    },
    "healthcare_social": {
        "Registered Nurse": {"nursing"},
        "General Practitioner": {"medical"},
        "Physiotherapist": {"therapy_rehabilitation"},
        "Pharmacy Technician": {"diagnostics_pharmacy"},
        "Care Worker": {"social_care"},
        "Paramedic": {"emergency_veterinary"},
    },
    "retail_sales_service": {
        "Sales Assistant": {"retail"},
        "Customer Service Agent": {"customer_service"},
        "Field Sales Representative": {"sales"},
    },
    "hospitality_tourism": {
        "Sous Chef": {"kitchen"},
        "Bartender": {"front_of_house"},
        "Hotel Receptionist": {"accommodation"},
        "Tour Guide": {"tourism_events"},
    },
    "office_finance_admin": {
        "Accountant": {"finance_accounting"},
        "Executive Assistant": {"administration"},
        "Paralegal": {"legal_compliance"},
        "Recruiter": {"hr_recruitment"},
    },
    "education_public_services": {
        "Primary School Teacher": {"teaching"},
        "Police Officer": {"public_safety"},
        "Personal Trainer": {"community_sports"},
        "Cleaner": {"facilities_support"},
    },
}


def test_each_pack_recognises_the_titles_of_its_field() -> None:
    from tests.prefilter_rules import rules_of

    for key, titles in EXPECTED.items():
        rules = rules_of(key)
        for title, areas in titles.items():
            assert areas <= rules.categorise([title]), (key, title)


def test_the_noise_of_a_pack_rules_a_posting_out() -> None:
    from tests.prefilter_rules import rules_of

    rules = rules_of("construction_trades")
    assert rules.categorise(["Electrician - talent pool"]) == frozenset()
    assert rules.categorise(["Electrician"]) == {"electrical"}


def test_a_software_owner_does_not_see_trades_titles_and_the_reverse() -> None:
    from tests.prefilter_rules import rules_of

    assert rules_of("software_data_it").categorise(["Maintenance Electrician"]) == frozenset()
    assert rules_of("construction_trades").categorise(["Senior Backend Engineer"]) == frozenset()


def test_the_areas_of_several_packs_add_up() -> None:
    from tests.prefilter_rules import rules_of

    both = rules_of("software_data_it", "construction_trades")
    assert both.categorise(["Electrician"]) == {"electrical"}
    assert both.categorise(["Backend Developer"]) == {"software"}
    assert len(both.areas) == 11


def test_every_pack_lists_credentials_people_in_the_field_hold() -> None:
    for pack in shipped_packs():
        assert len(pack.credentials) >= 3, pack.key
    names = {c.name for pack in shipped_packs() for c in pack.credentials}
    assert "Driving licence (category B)" in names
    assert "First aid certificate" in names


def test_a_credential_has_the_same_aliases_wherever_it_appears() -> None:
    seen: dict[str, tuple[str, ...]] = {}
    for pack in shipped_packs():
        for credential in pack.credentials:
            aliases = tuple(sorted(credential.aliases))
            assert seen.setdefault(credential.name.casefold(), aliases) == aliases, credential.name


# --- defaults for a new search intent (ADR-080, phase 6c) ----------------------------------------------


def test_every_pack_suggests_how_its_field_works() -> None:
    for pack in shipped_packs():
        assert pack.defaults is not None, pack.key
        assert pack.defaults.work_arrangements, pack.key


def test_trades_and_care_work_on_site_and_check_credentials() -> None:
    by_key = {pack.key: pack for pack in shipped_packs()}
    for key in ("construction_trades", "healthcare_social", "logistics_transport"):
        defaults = by_key[key].defaults
        assert defaults is not None
        assert defaults.work_arrangements["onsite"] == "preferred", key
        assert defaults.work_arrangements["remote"] == "rejected", key
        assert defaults.reject_missing_credentials is True, key
        assert defaults.weights.get("qualifications", 0) > 0, key


def test_the_software_pack_keeps_what_a_software_owner_already_has() -> None:
    (software,) = [p for p in shipped_packs() if p.key == "software_data_it"]
    assert software.defaults is not None
    assert software.defaults.work_arrangements["remote"] == "preferred"
    assert software.defaults.weights == {} and software.defaults.reject_missing_credentials is False

"""The pre-filter rules of the software pack, for tests that exercise area filtering."""

from jobs_radar.domain.prefilter import PrefilterRules
from jobs_radar.services.packs import shipped_packs
from jobs_radar.services.prefilter import rules_from_packs


def software_rules() -> PrefilterRules:
    """Rules of the software, data and IT pack: what the five fixed areas used to be."""
    return rules_from_packs([p for p in shipped_packs() if p.key == "software_data_it"])


def rules_of(*pack_keys: str) -> PrefilterRules:
    """Rules of the named shipped packs."""
    return rules_from_packs([p for p in shipped_packs() if p.key in pack_keys])

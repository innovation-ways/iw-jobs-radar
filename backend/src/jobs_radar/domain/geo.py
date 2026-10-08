"""Pure geography helpers: great-circle distance and place-name normalisation."""

import math
import re
import unicodedata

EARTH_RADIUS_KM = 6371.0088
_SPACES = re.compile(r"\s+")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two latitude/longitude points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def normalise_place(name: str) -> str:
    """Lowercase, drop accents and collapse spacing so ``Setúbal`` and ``setubal`` compare equal."""
    decomposed = unicodedata.normalize("NFKD", name)
    unaccented = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _SPACES.sub(" ", unaccented.casefold()).strip()

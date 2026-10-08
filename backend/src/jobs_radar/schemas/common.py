"""Shared building blocks for the strict, versioned JSON contracts (ADR-037, document 13)."""

from typing import Annotated
from zoneinfo import available_timezones

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints


class StrictModel(BaseModel):
    """Base class for every contract: unknown fields are rejected and instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


_REGION_GROUPS = frozenset({"EU", "EEA", "EUROPE", "UK", "WORLD"})
_TIMEZONES = available_timezones()


def _check_timezone(value: str) -> str:
    if value not in _TIMEZONES:
        msg = f"unknown IANA timezone: {value!r}"
        raise ValueError(msg)
    return value


def _check_region(value: str) -> str:
    # ISO 3166-1 alpha-2 country codes (two capitals) or one of the documented region groups.
    if len(value) == 2 and value.isalpha() and value.isupper():
        return value
    if value in _REGION_GROUPS:
        return value
    msg = f"invalid region {value!r}: use an ISO 3166-1 alpha-2 code or {sorted(_REGION_GROUPS)}"
    raise ValueError(msg)


IanaTimezone = Annotated[str, AfterValidator(_check_timezone)]
RegionCode = Annotated[str, AfterValidator(_check_region)]
CountryCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
LanguageCode = Annotated[str, StringConstraints(pattern=r"^[a-z]{2}$")]
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
TaxonomyKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=80)]
Money = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
Probability = Annotated[float, Field(ge=0, le=1)]
YearMonth = Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]

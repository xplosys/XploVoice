# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Country profiles for the launch markets (MP section 4, ADD-Q). Configuration, not hard-coded behaviour:
new markets are added here (and later in a country_profiles table, CR-016) without code changes elsewhere."""

from dataclasses import dataclass
from zoneinfo import available_timezones


@dataclass(frozen=True)
class Language:
    code: str
    name: str


@dataclass(frozen=True)
class CountryProfile:
    code: str
    name: str
    currency: str
    default_timezone: str
    timezones: tuple[str, ...]
    languages: tuple[Language, ...]
    date_format: str
    phone_region: str


COUNTRIES: dict[str, CountryProfile] = {
    "IN": CountryProfile(
        code="IN",
        name="India",
        currency="INR",
        default_timezone="Asia/Kolkata",
        timezones=("Asia/Kolkata",),
        languages=(Language("hi-IN", "Hindi"), Language("hi-Latn-IN", "Hinglish"), Language("en-IN", "Indian English")),
        date_format="DD/MM/YYYY",
        phone_region="IN",
    ),
    "US": CountryProfile(
        code="US",
        name="United States",
        currency="USD",
        default_timezone="America/New_York",
        timezones=(
            "America/New_York",
            "America/Chicago",
            "America/Denver",
            "America/Phoenix",
            "America/Los_Angeles",
            "America/Anchorage",
            "Pacific/Honolulu",
        ),
        languages=(Language("en-US", "US English"),),
        date_format="MM/DD/YYYY",
        phone_region="US",
    ),
}

_ALL_TZ = available_timezones()


def is_valid_timezone(tz: str) -> bool:
    return tz in _ALL_TZ

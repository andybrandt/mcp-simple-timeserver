"""
Core functionality shared between local and web MCP timeserver variants.

This module contains:
- NTP time fetching
- Timezone/location resolution (geocoding)
- Calendar formatting functions
- Shared tool implementation logic
"""
from datetime import datetime, timezone, timedelta, UTC
from importlib.metadata import version as get_version
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re

import ntplib
import pycountry
import requests
from hijridate import Gregorian
from japanera import EraDateTime
from pyluach import dates as hebrew_dates
from persiantools.jdatetime import JalaliDateTime
from timezonefinder import TimezoneFinder


# Default NTP server
DEFAULT_NTP_SERVER = 'pool.ntp.org'

# Nominatim API configuration (OpenStreetMap geocoding service)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_TIMEOUT = 5  # seconds

# Holiday API configuration
NAGER_API_URL = "https://date.nager.at/api/v3"
NAGER_TIMEOUT = 5  # seconds
OPENHOLIDAYS_API_URL = "https://openholidaysapi.org"
OPENHOLIDAYS_TIMEOUT = 5  # seconds

# Countries supported by OpenHolidaysAPI (for school holidays)
# Source: https://openholidaysapi.org/Countries
OPENHOLIDAYS_SUPPORTED_COUNTRIES = {
    "AD", "AL", "AT", "BE", "BG", "BR", "BY", "CH", "CZ", "DE",
    "EE", "ES", "FR", "HR", "HU", "IE", "IT", "LI", "LT", "LU",
    "LV", "MC", "MD", "MT", "MX", "NL", "PL", "PT", "RO", "RS",
    "SE", "SI", "SK", "SM", "VA", "ZA",
}

# Simple TTL cache for holiday data (24-hour TTL)
# Keys: "public:{country}:{year}", "public_oh:{country}:{year}",
#       "school:{country}:{year}", "subdivisions:{country}"
_holiday_cache: dict[str, tuple[datetime, any]] = {}
HOLIDAY_CACHE_TTL = timedelta(hours=24)


def _get_cached(key: str) -> Optional[any]:
    """
    Get a value from the holiday cache if it exists and hasn't expired.

    :param key: Cache key.
    :return: Cached value or None if not found or expired.
    """
    if key in _holiday_cache:
        cached_time, data = _holiday_cache[key]
        if datetime.now(UTC) - cached_time < HOLIDAY_CACHE_TTL:
            return data
        # Expired - remove from cache
        del _holiday_cache[key]
    return None


def _set_cached(key: str, data: any) -> None:
    """
    Store a value in the holiday cache with current timestamp.

    :param key: Cache key.
    :param data: Data to cache.
    """
    _holiday_cache[key] = (datetime.now(UTC), data)


# Holiday API functions


def fetch_public_holidays_nager(country_code: str, year: int) -> list[dict]:
    """
    Fetch public holidays from Nager.Date API.

    :param country_code: ISO 3166-1 alpha-2 country code (e.g., "PL").
    :param year: Year to fetch holidays for.
    :return: List of holiday dicts with keys: date, name, local_name, types, regional_codes.
             Returns empty list on error.
    """
    cache_key = f"public:{country_code}:{year}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    url = f"{NAGER_API_URL}/PublicHolidays/{year}/{country_code}"
    headers = {"User-Agent": _get_user_agent()}

    try:
        response = requests.get(url, headers=headers, timeout=NAGER_TIMEOUT)
        response.raise_for_status()
        raw_holidays = response.json()

        # Normalize the response to our internal format
        holidays = []
        for h in raw_holidays:
            holidays.append({
                "date": h.get("date", ""),
                "name": h.get("name", ""),
                "local_name": h.get("localName", ""),
                "types": h.get("types", []),
                "is_nationwide": h.get("global", True),
                "regional_codes": h.get("counties") or [],
            })

        _set_cached(cache_key, holidays)
        return holidays

    except (requests.RequestException, ValueError, KeyError):
        # Network errors, timeouts, invalid JSON, or missing fields
        return []


def fetch_subdivisions_openholidays(country_code: str) -> dict[str, str]:
    """
    Fetch subdivision code to name mapping from OpenHolidaysAPI.

    This converts region codes like "PL-MZ" to human-readable names like "Mazowieckie".

    :param country_code: ISO 3166-1 alpha-2 country code (e.g., "PL").
    :return: Dict mapping subdivision codes to names (e.g., {"PL-MZ": "Mazowieckie"}).
             Returns empty dict on error or if country not supported.
    """
    if country_code not in OPENHOLIDAYS_SUPPORTED_COUNTRIES:
        return {}

    cache_key = f"subdivisions:{country_code}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    url = f"{OPENHOLIDAYS_API_URL}/Subdivisions"
    params = {"countryIsoCode": country_code}
    headers = {"User-Agent": _get_user_agent()}

    try:
        response = requests.get(
            url, params=params, headers=headers, timeout=OPENHOLIDAYS_TIMEOUT
        )
        response.raise_for_status()
        raw_subdivisions = response.json()

        # Build code → name mapping
        # Prefer local name, fall back to English
        subdivisions = {}
        for sub in raw_subdivisions:
            code = sub.get("code", "")
            if not code:
                continue

            names = sub.get("name", [])
            # Get English name first as fallback
            en_name = ""
            local_name = ""
            for name_entry in names:
                lang = name_entry.get("language", "")
                text = name_entry.get("text", "")
                if lang == "EN":
                    en_name = text
                elif lang == country_code[:2]:
                    # Local language (e.g., "PL" for Poland)
                    local_name = text

            # Prefer local name, fallback to English, fallback to shortName
            display_name = local_name or en_name or sub.get("shortName", code)
            subdivisions[code] = display_name

        _set_cached(cache_key, subdivisions)
        return subdivisions

    except (requests.RequestException, ValueError, KeyError):
        return {}


def fetch_school_holidays_openholidays(
    country_code: str,
    year: int
) -> list[dict]:
    """
    Fetch school holidays from OpenHolidaysAPI.

    School holidays have date ranges and may be regional (varying by subdivision).

    :param country_code: ISO 3166-1 alpha-2 country code (e.g., "PL").
    :param year: Year to fetch holidays for.
    :return: List of school holiday dicts with keys: start_date, end_date, name,
             is_nationwide, regions (list of human-readable region names).
             Returns empty list on error or if country not supported.
    """
    if country_code not in OPENHOLIDAYS_SUPPORTED_COUNTRIES:
        return []

    cache_key = f"school:{country_code}:{year}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    # Get subdivision names for translating codes to names
    subdivisions = fetch_subdivisions_openholidays(country_code)

    url = f"{OPENHOLIDAYS_API_URL}/SchoolHolidays"
    params = {
        "countryIsoCode": country_code,
        "languageIsoCode": "EN",
        "validFrom": f"{year}-01-01",
        "validTo": f"{year}-12-31",
    }
    headers = {"User-Agent": _get_user_agent()}

    try:
        response = requests.get(
            url, params=params, headers=headers, timeout=OPENHOLIDAYS_TIMEOUT
        )
        response.raise_for_status()
        raw_holidays = response.json()

        # Normalize to our internal format
        holidays = []
        for h in raw_holidays:
            # Get name (prefer English)
            names = h.get("name", [])
            name = ""
            for name_entry in names:
                if name_entry.get("language") == "EN":
                    name = name_entry.get("text", "")
                    break
            if not name and names:
                name = names[0].get("text", "Unknown")

            # Convert subdivision codes to human-readable names
            raw_subdivisions = h.get("subdivisions", [])
            region_names = []
            for sub in raw_subdivisions:
                code = sub.get("code", "")
                if code in subdivisions:
                    region_names.append(subdivisions[code])
                elif code:
                    # Fallback to shortName if we don't have the mapping
                    region_names.append(sub.get("shortName", code))

            holidays.append({
                "start_date": h.get("startDate", ""),
                "end_date": h.get("endDate", ""),
                "name": name,
                "is_nationwide": h.get("nationwide", False),
                "regions": region_names,
            })

        _set_cached(cache_key, holidays)
        return holidays

    except (requests.RequestException, ValueError, KeyError):
        return []


def fetch_public_holidays_openholidays(
    country_code: str,
    year: int
) -> list[dict]:
    """
    Fetch public holidays from OpenHolidaysAPI (fallback for when Nager.Date fails).

    :param country_code: ISO 3166-1 alpha-2 country code (e.g., "PL").
    :param year: Year to fetch holidays for.
    :return: List of holiday dicts with same format as fetch_public_holidays_nager.
             Returns empty list on error or if country not supported.
    """
    if country_code not in OPENHOLIDAYS_SUPPORTED_COUNTRIES:
        return []

    cache_key = f"public_oh:{country_code}:{year}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    url = f"{OPENHOLIDAYS_API_URL}/PublicHolidays"
    params = {
        "countryIsoCode": country_code,
        "languageIsoCode": "EN",
        "validFrom": f"{year}-01-01",
        "validTo": f"{year}-12-31",
    }
    headers = {"User-Agent": _get_user_agent()}

    try:
        response = requests.get(
            url, params=params, headers=headers, timeout=OPENHOLIDAYS_TIMEOUT
        )
        response.raise_for_status()
        raw_holidays = response.json()

        # Normalize to same format as Nager
        holidays = []
        for h in raw_holidays:
            # Get English name
            names = h.get("name", [])
            name = ""
            for name_entry in names:
                if name_entry.get("language") == "EN":
                    name = name_entry.get("text", "")
                    break
            if not name and names:
                name = names[0].get("text", "Unknown")

            holidays.append({
                "date": h.get("startDate", ""),
                "name": name,
                "local_name": name,  # OpenHolidays doesn't give local name separately
                "types": [h.get("type", "Public")],
                "is_nationwide": h.get("nationwide", True),
                "regional_codes": [],
            })

        _set_cached(cache_key, holidays)
        return holidays

    except (requests.RequestException, ValueError, KeyError):
        return []


# Country code resolution


def resolve_country_code(country: str) -> Optional[str]:
    """
    Resolve a country name or code to its ISO 3166-1 alpha-2 code.

    Supports various input formats:
    - Full names: "Poland", "United States", "Germany"
    - Common names: "USA", "UK", "Great Britain"
    - Alpha-2 codes: "PL", "US", "DE"
    - Alpha-3 codes: "POL", "USA", "DEU"
    - Local language names: "Deutschland", "Polska", "España"

    :param country: Country name or code to resolve.
    :return: ISO 3166-1 alpha-2 code (e.g., "PL") or None if not found.
    """
    country = country.strip()
    if not country:
        return None

    # Common aliases that pycountry doesn't handle well
    # (fuzzy search can match wrong countries for these)
    COMMON_ALIASES = {
        "uk": "GB",
        "england": "GB",
        "scotland": "GB",
        "wales": "GB",
        "britain": "GB",
        "deutschland": "DE",
        "polska": "PL",
        "españa": "ES",
        "espana": "ES",
        "italia": "IT",
        "france": "FR",
        "nederland": "NL",
        "holland": "NL",
        "česko": "CZ",
        "cesko": "CZ",
        "czechia": "CZ",
        "schweiz": "CH",
        "suisse": "CH",
        "svizzera": "CH",
        "österreich": "AT",
        "osterreich": "AT",
    }

    country_lower = country.lower()
    if country_lower in COMMON_ALIASES:
        return COMMON_ALIASES[country_lower]

    # Try direct lookup by alpha-2 code (case-insensitive)
    country_upper = country.upper()
    if len(country_upper) == 2:
        try:
            result = pycountry.countries.get(alpha_2=country_upper)
            if result:
                return result.alpha_2
        except (KeyError, LookupError):
            pass

    # Try direct lookup by alpha-3 code
    if len(country_upper) == 3:
        try:
            result = pycountry.countries.get(alpha_3=country_upper)
            if result:
                return result.alpha_2
        except (KeyError, LookupError):
            pass

    # Try lookup by name (exact match)
    try:
        result = pycountry.countries.get(name=country)
        if result:
            return result.alpha_2
    except (KeyError, LookupError):
        pass

    # Try lookup by common name (e.g., "United States" vs "United States of America")
    try:
        result = pycountry.countries.get(common_name=country)
        if result:
            return result.alpha_2
    except (KeyError, LookupError):
        pass

    # Try lookup by official name
    try:
        result = pycountry.countries.get(official_name=country)
        if result:
            return result.alpha_2
    except (KeyError, LookupError):
        pass

    # Try fuzzy search as last resort
    try:
        results = pycountry.countries.search_fuzzy(country)
        if results:
            return results[0].alpha_2
    except (LookupError, Exception):
        pass

    return None


def _get_user_agent() -> str:
    """
    Get User-Agent string with current package version.

    Uses importlib.metadata to read version from installed package,
    ensuring we have a single source of truth (pyproject.toml).
    """
    try:
        pkg_version = get_version("mcp-simple-timeserver")
    except Exception:
        pkg_version = "unknown"
    return f"mcp-simple-timeserver/{pkg_version}"


# Lazy-loaded TimezoneFinder instance
# Note on timezonefinder data model:
# - Shape data (~40MB) is BUNDLED with the pip package (no runtime download)
# - Data is stored in site-packages/timezonefinder/
# - On first use, data is loaded into RAM (not fetched from network)
# - Web server: long-lived process, init once, reuse across all requests (fast)
# - Local stdio: new process per session, ~1-2s init cost on first location call
_timezone_finder: Optional[TimezoneFinder] = None


def _get_timezone_finder() -> TimezoneFinder:
    """
    Get or create the TimezoneFinder instance (lazy initialization).

    TimezoneFinder loads shape data into memory on first instantiation.
    We use a singleton pattern to avoid repeated loading within a process.
    """
    global _timezone_finder
    if _timezone_finder is None:
        _timezone_finder = TimezoneFinder()
    return _timezone_finder


# Geocoding and timezone resolution functions

def geocode_location(query: str) -> Optional[tuple[float, float, str]]:
    """
    Resolve a location name (city/country) to coordinates using Nominatim.

    :param query: Location name (e.g., "Warsaw", "Poland", "New York, USA")
    :return: Tuple of (latitude, longitude, display_name) or None if not found.
    """
    headers = {"User-Agent": _get_user_agent()}
    params = {
        "q": query,
        "format": "json",
        "limit": 1,  # We only need the top result
        "addressdetails": 1,  # Get structured address for display name
    }

    try:
        response = requests.get(
            NOMINATIM_URL,
            params=params,
            headers=headers,
            timeout=NOMINATIM_TIMEOUT
        )
        response.raise_for_status()
        results = response.json()

        if results:
            result = results[0]
            lat = float(result["lat"])
            lon = float(result["lon"])
            display_name = result.get("display_name", query)
            # Simplify display name: take first two parts (typically city, country)
            parts = display_name.split(", ")
            if len(parts) > 2:
                display_name = f"{parts[0]}, {parts[-1]}"
            return (lat, lon, display_name)

    except (requests.RequestException, ValueError, KeyError):
        # Network errors, timeouts, invalid JSON, or missing fields
        pass

    return None


def geocode_location_detailed(
    query: str
) -> Optional[tuple[str, Optional[str], str]]:
    """
    Resolve a location name to country and subdivision using Nominatim.

    This is used for holiday lookups where we need both the country code
    and the subdivision/region name for filtering regional holidays.

    :param query: Location name (e.g., "Warsaw", "Krakow", "Berlin")
    :return: Tuple of (country_code, subdivision_name, display_name) or None if not found.
             country_code: ISO 3166-1 alpha-2 code (e.g., "PL", "DE")
             subdivision_name: State/region/voivodeship name (e.g., "Mazowieckie", "Bayern")
             display_name: Human-readable location name for display
    """
    headers = {"User-Agent": _get_user_agent()}
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
        "addressdetails": 1,  # Get structured address components
    }

    try:
        response = requests.get(
            NOMINATIM_URL,
            params=params,
            headers=headers,
            timeout=NOMINATIM_TIMEOUT
        )
        response.raise_for_status()
        results = response.json()

        if results:
            result = results[0]
            address = result.get("address", {})

            # Extract country code (Nominatim returns lowercase ISO code)
            country_code = address.get("country_code", "").upper()
            if not country_code:
                return None

            # Extract subdivision name from address components
            # Nominatim uses different keys depending on the country
            subdivision_name = None
            for key in ["state", "region", "province", "county", "state_district"]:
                if key in address:
                    subdivision_name = address[key]
                    break

            # Build display name
            display_name = result.get("display_name", query)
            parts = display_name.split(", ")
            if len(parts) > 2:
                display_name = f"{parts[0]}, {parts[-1]}"

            return (country_code, subdivision_name, display_name)

    except (requests.RequestException, ValueError, KeyError):
        pass

    return None


def find_subdivision_code(
    country_code: str,
    subdivision_name: str
) -> Optional[str]:
    """
    Find the OpenHolidaysAPI subdivision code from a subdivision name.

    This performs a reverse lookup: given "Mazowieckie" returns "PL-MZ".
    Uses the subdivision mapping from OpenHolidaysAPI.

    :param country_code: ISO 3166-1 alpha-2 country code (e.g., "PL").
    :param subdivision_name: Subdivision name to find (e.g., "Mazowieckie").
    :return: Subdivision code (e.g., "PL-MZ") or None if not found.
    """
    if country_code not in OPENHOLIDAYS_SUPPORTED_COUNTRIES:
        return None

    subdivisions = fetch_subdivisions_openholidays(country_code)
    if not subdivisions:
        return None

    # Normalize the search name
    search_name = subdivision_name.lower().strip()

    # Try exact match first, then partial match
    for code, name in subdivisions.items():
        if name.lower() == search_name:
            return code

    # Try partial match (e.g., "Mazowieckie" might match "Województwo Mazowieckie")
    for code, name in subdivisions.items():
        if search_name in name.lower() or name.lower() in search_name:
            return code

    return None


def coords_to_timezone(lat: float, lon: float) -> Optional[str]:
    """
    Convert coordinates to IANA timezone name using timezonefinder.

    :param lat: Latitude in degrees.
    :param lon: Longitude in degrees.
    :return: IANA timezone name (e.g., "Europe/Warsaw") or None if not found.
    """
    tf = _get_timezone_finder()
    try:
        return tf.timezone_at(lat=lat, lng=lon)
    except Exception:
        return None


def parse_timezone_param(tz_str: str) -> Optional[ZoneInfo]:
    """
    Parse a timezone parameter string into a ZoneInfo object.

    Supports:
    - IANA timezone names (e.g., "Europe/Warsaw", "America/New_York")
    - UTC offset format (e.g., "+02:00", "-05:00", "+0530")

    :param tz_str: Timezone string to parse.
    :return: ZoneInfo object or None if invalid.
    """
    tz_str = tz_str.strip()
    if not tz_str:
        return None

    # Try IANA timezone name first
    try:
        return ZoneInfo(tz_str)
    except (ZoneInfoNotFoundError, KeyError):
        pass

    # Try UTC offset format: +HH:MM, -HH:MM, +HHMM, -HHMM
    offset_pattern = r'^([+-])(\d{2}):?(\d{2})$'
    match = re.match(offset_pattern, tz_str)
    if match:
        sign = 1 if match.group(1) == '+' else -1
        hours = int(match.group(2))
        minutes = int(match.group(3))
        offset_seconds = sign * (hours * 3600 + minutes * 60)
        return timezone(timedelta(seconds=offset_seconds))

    return None


def resolve_location(
    tz: str = "",
    country: str = "",
    city: str = ""
) -> tuple[Optional[ZoneInfo], str, Optional[str]]:
    """
    Resolve location parameters to a timezone.

    Priority: timezone > city > country (if multiple provided).

    :param tz: Direct timezone specification (IANA name or UTC offset).
    :param country: Country name or code.
    :param city: City name.
    :return: Tuple of (timezone_object, location_name, warning_message).
             If resolution fails, timezone_object is None and warning is set.
    """
    # Priority 1: Direct timezone parameter
    if tz.strip():
        tz_obj = parse_timezone_param(tz)
        if tz_obj:
            # Format the timezone name for display
            if isinstance(tz_obj, ZoneInfo):
                tz_name = str(tz_obj)
            else:
                # For fixed offset timezones
                tz_name = tz.strip()
            return (tz_obj, tz_name, None)
        else:
            return (
                None,
                "",
                f'Could not parse timezone "{tz}". '
                'Use IANA format (e.g., "Europe/Warsaw") or UTC offset (e.g., "+02:00").'
            )

    # Priority 2: City parameter
    if city.strip():
        geo_result = geocode_location(city.strip())
        if geo_result:
            lat, lon, display_name = geo_result
            tz_name = coords_to_timezone(lat, lon)
            if tz_name:
                try:
                    tz_obj = ZoneInfo(tz_name)
                    return (tz_obj, display_name, None)
                except (ZoneInfoNotFoundError, KeyError):
                    pass
        return (
            None,
            "",
            f'Could not resolve location "{city}". '
            'Try a major city name, provide country name, or use timezone parameter '
            '(e.g., "Europe/Warsaw").'
        )

    # Priority 3: Country parameter
    if country.strip():
        geo_result = geocode_location(country.strip())
        if geo_result:
            lat, lon, display_name = geo_result
            tz_name = coords_to_timezone(lat, lon)
            if tz_name:
                try:
                    tz_obj = ZoneInfo(tz_name)
                    return (tz_obj, display_name, None)
                except (ZoneInfoNotFoundError, KeyError):
                    pass
        return (
            None,
            "",
            f'Could not resolve country "{country}". '
            'Try a city name or use timezone parameter (e.g., "Europe/Warsaw").'
        )

    # No location parameters provided
    return (None, "", None)


def get_ntp_datetime(server: str = DEFAULT_NTP_SERVER) -> tuple[datetime, bool]:
    """
    Fetches accurate UTC time from an NTP server.

    :param server: NTP server address to query.
    :return: A tuple of (datetime, is_ntp_time). If NTP fails, falls back to
             local time with is_ntp_time=False.
    """
    try:
        ntp_client = ntplib.NTPClient()
        response = ntp_client.request(server, version=3)
        return datetime.fromtimestamp(response.tx_time, tz=UTC), True
    except (ntplib.NTPException, OSError):
        # Catches NTP errors, socket timeouts, and network errors
        return datetime.now(tz=UTC), False


# Calendar formatting functions

def format_unix(ntp_time: datetime) -> str:
    """Format time as Unix timestamp."""
    timestamp = int(ntp_time.timestamp())
    return f"--- Unix Timestamp ---\n{timestamp}"


def format_isodate(ntp_time: datetime) -> str:
    """Format time as ISO 8601 week date."""
    iso_week_date = ntp_time.strftime("%G-W%V-%u")
    return f"--- ISO Week Date ---\n{iso_week_date}"


def calendar_hijri(ntp_time: datetime) -> str:
    """Format time in Hijri (Islamic) calendar."""
    hijri = Gregorian.fromdate(ntp_time.date()).to_hijri()
    hijri_formatted = hijri.isoformat()
    month_name = hijri.month_name()
    day_name = hijri.day_name()
    notation = hijri.notation()
    return (
        f"--- Hijri Calendar ---\n"
        f"Date: {hijri_formatted} {notation}\n"
        f"Month: {month_name}\n"
        f"Day: {day_name}"
    )


def calendar_japanese(ntp_time: datetime) -> str:
    """Format time in Japanese Era calendar (both English and Kanji)."""
    era_datetime = EraDateTime.from_datetime(ntp_time)
    # English format: Reiwa 7, January 15, 14:00
    english_formatted = era_datetime.strftime("%-E %-Y, %B %d, %H:%M")
    # Kanji format: 令和7年01月15日 14時
    kanji_formatted = era_datetime.strftime("%-K%-y年%m月%d日 %H時")
    era_english = era_datetime.era.english
    era_kanji = era_datetime.era.kanji
    return (
        f"--- Japanese Calendar ---\n"
        f"English: {english_formatted}\n"
        f"Kanji: {kanji_formatted}\n"
        f"Era: {era_english} ({era_kanji})"
    )


def calendar_persian(ntp_time: datetime) -> str:
    """Format time in Persian (Jalali) calendar (both English and Farsi)."""
    jalali_dt = JalaliDateTime(ntp_time)
    english_formatted = jalali_dt.strftime("%A %d %B %Y", locale="en")
    farsi_formatted = jalali_dt.strftime("%A %d %B %Y", locale="fa")
    return (
        f"--- Persian Calendar ---\n"
        f"English: {english_formatted}\n"
        f"Farsi: {farsi_formatted}"
    )


def calendar_hebrew(ntp_time: datetime) -> str:
    """Format time in Hebrew (Jewish) calendar (both English and Hebrew)."""
    gregorian_date = hebrew_dates.GregorianDate(
        ntp_time.year, ntp_time.month, ntp_time.day
    )
    hebrew_date = gregorian_date.to_heb()
    english_formatted = f"{hebrew_date.day} {hebrew_date.month_name()} {hebrew_date.year}"
    hebrew_formatted = hebrew_date.hebrew_date_string()

    # Check for holiday in both languages
    holiday_en = hebrew_date.holiday(hebrew=False)
    holiday_he = hebrew_date.holiday(hebrew=True)
    holiday_line = ""
    if holiday_en:
        holiday_line = f"\nHoliday: {holiday_en} ({holiday_he})"

    return (
        f"--- Hebrew Calendar ---\n"
        f"English: {english_formatted}\n"
        f"Hebrew: {hebrew_formatted}"
        f"{holiday_line}"
    )


# Mapping of calendar names to their formatting functions
CALENDAR_FORMATTERS = {
    "unix": format_unix,
    "isodate": format_isodate,
    "hijri": calendar_hijri,
    "japanese": calendar_japanese,
    "persian": calendar_persian,
    "hebrew": calendar_hebrew,
}


# Shared tool implementation functions

def utc_time_result(server: str = DEFAULT_NTP_SERVER) -> str:
    """
    Generate the result string for get_utc tool.

    :param server: NTP server address to query.
    :return: Formatted UTC time string.
    """
    utc_time, is_ntp = get_ntp_datetime(server)
    formatted_time = utc_time.strftime("%Y-%m-%d %H:%M:%S")
    day_of_week = utc_time.strftime("%A")
    fallback_notice = "" if is_ntp else "\n(Note: NTP unavailable, using local server time)"
    return f"Current UTC Time from {server}: {formatted_time}\nDay: {day_of_week}{fallback_notice}"


def _format_utc_offset(dt: datetime) -> str:
    """
    Format the UTC offset of a datetime as +HH:MM or -HH:MM.

    :param dt: Timezone-aware datetime object.
    :return: Formatted offset string (e.g., "+01:00", "-05:00").
    """
    offset = dt.utcoffset()
    if offset is None:
        return "+00:00"

    total_seconds = int(offset.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    total_seconds = abs(total_seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{sign}{hours:02d}:{minutes:02d}"


def _get_timezone_abbrev(dt: datetime) -> str:
    """
    Get the timezone abbreviation (e.g., CET, EST, JST) for a datetime.

    :param dt: Timezone-aware datetime object.
    :return: Timezone abbreviation or empty string if not available.
    """
    abbrev = dt.strftime("%Z")
    # Filter out numeric-only abbreviations (some systems return offset as abbrev)
    if abbrev and not abbrev.lstrip("+-").isdigit():
        return abbrev
    return ""


def _is_dst_active(dt: datetime) -> Optional[bool]:
    """
    Check if DST is active for a given datetime.

    :param dt: Timezone-aware datetime object.
    :return: True if DST active, False if not, None if unknown.
    """
    dst = dt.dst()
    if dst is None:
        return None
    return dst.total_seconds() > 0


def _extract_country_code_from_location(
    country_param: str,
    location_name: str
) -> Optional[str]:
    """
    Try to extract country code from location parameters.

    :param country_param: Direct country parameter if provided.
    :param location_name: Location display name (e.g., "Warsaw, Poland").
    :return: ISO country code or None if not determinable.
    """
    # If country parameter was provided, use it directly
    if country_param.strip():
        return resolve_country_code(country_param)

    # Try to extract country from location_name (typically "City, Country" format)
    if location_name:
        parts = location_name.split(", ")
        if len(parts) >= 2:
            # Last part is typically the country
            country_name = parts[-1].strip()
            return resolve_country_code(country_name)

    return None


def current_time_result(
    calendar: str = "",
    tz: str = "",
    country: str = "",
    city: str = ""
) -> str:
    """
    Generate the result string for get_current_time tool.

    :param calendar: Comma-separated list of calendar formats to include.
    :param tz: Direct timezone specification (IANA name or UTC offset).
    :param country: Country name or code for timezone lookup.
    :param city: City name for timezone lookup (primary use case).
    :return: Formatted time string with optional location and calendar conversions.
    """
    # Get accurate UTC time from NTP
    utc_time, is_ntp = get_ntp_datetime()

    # Try to resolve location to timezone
    tz_obj, location_name, location_warning = resolve_location(tz, country, city)

    # Determine which time to use for display and calendars
    # If location specified, use local time; otherwise use UTC
    has_location = bool(tz.strip() or country.strip() or city.strip())

    if tz_obj:
        # Successfully resolved timezone - convert to local time
        local_time = utc_time.astimezone(tz_obj)
        display_time = local_time
    else:
        # No timezone or resolution failed - use UTC
        display_time = utc_time

    # Format times
    formatted_display_time = display_time.strftime("%Y-%m-%d %H:%M:%S")
    formatted_utc_time = utc_time.strftime("%Y-%m-%d %H:%M:%S")
    day_of_week = display_time.strftime("%A")
    gregorian_date = display_time.strftime("%Y-%m-%d")

    # Build result based on whether location was requested
    result_lines = []
    warnings = []
    calendar_sections = []

    if has_location:
        if tz_obj:
            # Successfully resolved location - show local time info
            result_lines.append(f"Local Time: {formatted_display_time}")
            result_lines.append(f"Day: {day_of_week}")
            result_lines.append(f"Location: {location_name}")

            # Build timezone info line with abbreviation if available
            tz_abbrev = _get_timezone_abbrev(display_time)
            if tz_abbrev:
                # For IANA timezones, show name and abbreviation
                if isinstance(tz_obj, ZoneInfo):
                    result_lines.append(f"Timezone: {tz_obj} ({tz_abbrev})")
                else:
                    result_lines.append(f"Timezone: {tz_abbrev}")
            else:
                # No abbreviation available
                if isinstance(tz_obj, ZoneInfo):
                    result_lines.append(f"Timezone: {tz_obj}")
                else:
                    result_lines.append(f"Timezone: {location_name}")

            # UTC offset
            offset_str = _format_utc_offset(display_time)
            result_lines.append(f"UTC Offset: {offset_str}")

            # DST status (only for IANA timezones, not fixed offsets)
            if isinstance(tz_obj, ZoneInfo):
                dst_active = _is_dst_active(display_time)
                if dst_active is not None:
                    dst_text = "Yes" if dst_active else "No"
                    result_lines.append(f"DST Active: {dst_text}")

            # Check if today is a public holiday
            country_code = _extract_country_code_from_location(country, location_name)
            if country_code:
                today_str = display_time.strftime("%Y-%m-%d")
                year = display_time.year
                holidays = fetch_public_holidays_nager(country_code, year)
                if not holidays and country_code in OPENHOLIDAYS_SUPPORTED_COUNTRIES:
                    holidays = fetch_public_holidays_openholidays(country_code, year)

                for h in holidays:
                    if h.get("date") == today_str:
                        name = h.get("name", "")
                        local_name = h.get("local_name", "")
                        if local_name and local_name != name:
                            result_lines.append(
                                f"Today is: {name} ({local_name}) - Public Holiday"
                            )
                        else:
                            result_lines.append(f"Today is: {name} - Public Holiday")
                        break
        else:
            # Location resolution failed - show warning and fall back to UTC
            if location_warning:
                warnings.append(f"Note: {location_warning}")
                warnings.append(
                    'Tip: Try a major city name, provide country name, '
                    'or use timezone parameter (e.g., "Europe/Warsaw").'
                )
            result_lines.append(f"UTC Time: {formatted_utc_time}")
            result_lines.append(f"Day: {day_of_week}")
    else:
        # No location requested - original behavior (UTC only)
        result_lines.append(f"UTC Time: {formatted_utc_time}")
        result_lines.append(f"Day: {day_of_week}")

    # Process requested calendars if any
    # Calendars use display_time (local if available, UTC otherwise)
    if calendar.strip():
        # Add the Gregorian date line when calendars are requested
        result_lines.append(f"Date: {gregorian_date} (Gregorian)")

        requested = [c.strip().lower() for c in calendar.split(",")]
        for cal_name in requested:
            if not cal_name:
                continue
            if cal_name in CALENDAR_FORMATTERS:
                calendar_sections.append(CALENDAR_FORMATTERS[cal_name](display_time))
            else:
                warnings.append(f"(Note: Unknown calendar format ignored: {cal_name})")

    # Build final result
    # Start with any warnings (for failed location resolution)
    result_parts = []

    if warnings and has_location and not tz_obj:
        # Put warnings at the top for failed location resolution
        result_parts.append("\n".join(warnings))
        result_parts.append("")  # Blank line

    result_parts.append("\n".join(result_lines))

    if calendar_sections:
        result_parts.append("\n" + "\n\n".join(calendar_sections))

    # Add calendar warnings (unknown formats) at the end
    calendar_warnings = [w for w in warnings if "Unknown calendar" in w]
    if calendar_warnings:
        result_parts.append("\n" + "\n".join(calendar_warnings))

    # Add UTC reference time at the end when showing local time
    if has_location and tz_obj:
        result_parts.append(f"\nUTC Time: {formatted_utc_time}")

    # Add fallback notice if NTP was unavailable
    if not is_ntp:
        result_parts.append("(Note: NTP unavailable, using local server time)")

    return "\n".join(result_parts)


# Time distance calculation functions

def parse_date_input(
    date_str: str,
    tz_obj: Optional[ZoneInfo],
    ntp_time: Optional[datetime] = None
) -> datetime:
    """
    Parse a date/datetime string into a timezone-aware datetime object.

    Supports:
    - "now" - Returns current NTP time (converted to timezone if provided)
    - "YYYY-MM-DD" - Date only (time set to midnight in the given timezone)
    - "YYYY-MM-DDTHH:MM:SS" - Full datetime (assumed to be in given timezone)

    :param date_str: The date string to parse.
    :param tz_obj: Timezone to use for interpretation (None for UTC).
    :param ntp_time: Current NTP time in UTC (required when date_str is "now").
    :return: Timezone-aware datetime object.
    :raises ValueError: If date string cannot be parsed.
    """
    date_str = date_str.strip().lower()

    # Determine the effective timezone
    effective_tz = tz_obj if tz_obj else timezone.utc

    if date_str == "now":
        if ntp_time is None:
            raise ValueError('NTP time must be provided when parsing "now"')
        # Return current time in the effective timezone
        if tz_obj:
            return ntp_time.astimezone(tz_obj)
        return ntp_time

    # Try to parse as ISO format
    try:
        # Check if it has a time component
        has_time = "t" in date_str or " " in date_str

        if has_time:
            # Parse with time component
            # Handle both 'T' separator and space separator
            parsed = datetime.fromisoformat(date_str.replace(" ", "T"))
        else:
            # Parse date only, set time to midnight
            parsed = datetime.fromisoformat(date_str)
            parsed = datetime.combine(parsed.date(), datetime.min.time())

        # Make timezone-aware if naive
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=effective_tz)

        return parsed

    except ValueError as e:
        raise ValueError(
            f'Could not parse date "{date_str}". '
            'Use ISO 8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS) or "now".'
        ) from e


def format_duration_human(total_seconds: int) -> tuple[str, str]:
    """
    Format a duration in seconds into human-readable components.

    :param total_seconds: Duration in seconds (uses absolute value).
    :return: Tuple of (detailed breakdown, simplified summary).
             Example: ("15 days, 3 hours, 45 minutes, 30 seconds", "2 weeks and 1 day")
    """
    # Work with absolute value for formatting
    seconds = abs(total_seconds)

    # Calculate all components
    weeks, remainder = divmod(seconds, 7 * 24 * 3600)
    days, remainder = divmod(remainder, 24 * 3600)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    # Build detailed breakdown (days, hours, minutes, seconds)
    total_days = weeks * 7 + days
    detail_parts = []
    if total_days > 0:
        detail_parts.append(f"{total_days} day{'s' if total_days != 1 else ''}")
    if hours > 0:
        detail_parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        detail_parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if secs > 0 or not detail_parts:
        detail_parts.append(f"{secs} second{'s' if secs != 1 else ''}")

    detailed = ", ".join(detail_parts)

    # Build simplified summary (weeks and days only for longer durations)
    summary_parts = []
    if weeks > 0:
        summary_parts.append(f"{weeks} week{'s' if weeks != 1 else ''}")
    if days > 0:
        summary_parts.append(f"{days} day{'s' if days != 1 else ''}")

    if summary_parts:
        simplified = " and ".join(summary_parts)
    elif hours > 0:
        simplified = f"{hours} hour{'s' if hours != 1 else ''}"
    elif minutes > 0:
        simplified = f"{minutes} minute{'s' if minutes != 1 else ''}"
    else:
        simplified = f"{secs} second{'s' if secs != 1 else ''}"

    return detailed, simplified


def format_duration_by_unit(total_seconds: int, unit: str) -> str:
    """
    Format duration as a single unit.

    :param total_seconds: Duration in seconds (uses absolute value).
    :param unit: One of "days", "weeks", "hours", "minutes", "seconds".
    :return: Formatted string with the value in the specified unit.
    """
    seconds = abs(total_seconds)

    if unit == "weeks":
        value = seconds / (7 * 24 * 3600)
        return f"{value:.2f} weeks"
    elif unit == "days":
        value = seconds / (24 * 3600)
        return f"{value:.2f} days"
    elif unit == "hours":
        value = seconds / 3600
        return f"{value:.2f} hours"
    elif unit == "minutes":
        value = seconds / 60
        return f"{value:.2f} minutes"
    else:  # seconds
        return f"{seconds} seconds"


def count_business_days(
    from_dt: datetime,
    to_dt: datetime,
    exclude_holidays: bool = False,
    country_code: Optional[str] = None
) -> tuple[int, int, int, list[str]]:
    """
    Count business days between two dates.

    Returns: (business_days, weekend_days, holidays_excluded, holiday_names)
    """
    start_date = from_dt.date()
    end_date = to_dt.date()
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    holiday_dates = set()
    holiday_names_by_date = {}

    # Fetch holidays once per year if requested
    if exclude_holidays and country_code:
        # Include the end year (range upper bound is exclusive).
        for year in range(start_date.year, end_date.year + 1):
            holidays = fetch_public_holidays_nager(country_code, year)
            if not holidays and country_code in OPENHOLIDAYS_SUPPORTED_COUNTRIES:
                holidays = fetch_public_holidays_openholidays(country_code, year)

            for holiday in holidays:
                date_str = holiday.get("date", "")
                if not date_str:
                    continue
                try:
                    holiday_date = datetime.fromisoformat(date_str).date()
                except ValueError:
                    continue

                if holiday_date < start_date or holiday_date > end_date:
                    continue

                holiday_dates.add(holiday_date)

                name = holiday.get("name", "")
                local_name = holiday.get("local_name", "")
                if local_name and local_name != name:
                    display_name = f"{name} ({local_name})" if name else local_name
                else:
                    display_name = name or local_name

                if display_name:
                    holiday_names_by_date.setdefault(holiday_date, [])
                    if display_name not in holiday_names_by_date[holiday_date]:
                        holiday_names_by_date[holiday_date].append(display_name)

    business_days = 0
    weekend_days = 0
    holidays_excluded = 0
    holiday_names = []

    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() >= 5:
            weekend_days += 1
        elif exclude_holidays and country_code and current_date in holiday_dates:
            holidays_excluded += 1
            for name in holiday_names_by_date.get(current_date, []):
                if name not in holiday_names:
                    holiday_names.append(name)
        else:
            business_days += 1

        current_date += timedelta(days=1)

    return business_days, weekend_days, holidays_excluded, holiday_names


def time_distance_result(
    from_date: str = "now",
    to_date: str = "now",
    unit: str = "auto",
    tz: str = "",
    country: str = "",
    city: str = "",
    business_days: bool = False,
    exclude_holidays: bool = False
) -> str:
    """
    Calculate the duration between two dates/datetimes.

    :param from_date: Start date (ISO 8601 or "now").
    :param to_date: End date (ISO 8601 or "now").
    :param unit: Output unit - "auto", "days", "weeks", "hours", "minutes", "seconds".
    :param tz: Direct timezone specification (IANA name or UTC offset).
    :param country: Country name for timezone lookup.
    :param city: City name for timezone lookup.
    :return: Formatted result string with duration information.
    """
    # Normalize inputs
    from_date = from_date.strip().lower() if from_date else "now"
    to_date = to_date.strip().lower() if to_date else "now"

    # Quick check: if both parameters are identical strings, return error immediately
    # This handles both "now"/"now" case and identical explicit dates
    if from_date == to_date and not business_days:
        return "Distance: 0 (same parameters, error?)"

    # Resolve timezone if location parameters provided
    tz_obj, location_name, location_warning = resolve_location(tz, country, city)

    # Handle location resolution errors
    result_lines = []
    if location_warning:
        result_lines.append(f"Note: {location_warning}")
        result_lines.append("Using UTC for calculations.")
        result_lines.append("")

    # Determine if we need NTP time (only if exactly one param is "now")
    from_is_now = from_date == "now"
    to_is_now = to_date == "now"
    ntp_time = None
    is_ntp = True

    if from_is_now or to_is_now:
        ntp_time, is_ntp = get_ntp_datetime()

    # Parse both dates
    try:
        from_dt = parse_date_input(from_date, tz_obj, ntp_time)
    except ValueError as e:
        return str(e)

    try:
        to_dt = parse_date_input(to_date, tz_obj, ntp_time)
    except ValueError as e:
        return str(e)

    # Check if parsed datetimes are equal (handles different string formats resolving to same time)
    if from_dt == to_dt and not business_days:
        return "Distance: 0 (same parameters, error?)"

    # Calculate the difference
    delta = to_dt - from_dt
    total_seconds = int(delta.total_seconds())

    # Determine direction
    if total_seconds > 0:
        direction = "future"
    else:
        direction = "past"

    if business_days:
        # Get country code for holiday exclusion
        country_code = None
        if exclude_holidays:
            country_code = _extract_country_code_from_location(country, location_name)
            if not country_code:
                result_lines.append(
                    "Note: Could not determine country for holiday exclusion."
                )
                result_lines.append(
                    "Business days calculated without holiday exclusion."
                )
                result_lines.append("")

        biz_days, weekends, holidays_count, holiday_names = count_business_days(
            from_dt,
            to_dt,
            exclude_holidays and country_code is not None,
            country_code
        )

        # Format output (calendar-based, inclusive)
        calendar_days = abs((to_dt.date() - from_dt.date()).days) + 1
        result_lines.append(f"Distance: {biz_days} business days")
        breakdown = f"{calendar_days} calendar days - {weekends} weekend days"
        if exclude_holidays and country_code:
            breakdown += f" - {holidays_count} holidays"
        result_lines.append(f"Breakdown: {breakdown}")

        if holiday_names:
            # Truncated list: show first 3 names + "and X more" if longer
            max_holiday_names = 3
            if len(holiday_names) <= max_holiday_names:
                result_lines.append(f"Holidays excluded: {', '.join(holiday_names)}")
            else:
                shown = ", ".join(holiday_names[:max_holiday_names])
                remaining = len(holiday_names) - max_holiday_names
                result_lines.append(
                    f"Holidays excluded: {shown}, and {remaining} more"
                )

        # Standard output sections (same as non-business mode)
        result_lines.append(f"Direction: {direction}")
        result_lines.append("")
        result_lines.append(f"From: {from_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        result_lines.append(f"To: {to_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        if location_name:
            result_lines.append(f"Location: {location_name}")
        result_lines.append("")
        result_lines.append("UTC Reference:")
        from_utc = from_dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        to_utc = to_dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        result_lines.append(f"  From: {from_utc} UTC")
        result_lines.append(f"  To: {to_utc} UTC")
    else:
        # Format duration based on unit
        valid_units = ["auto", "days", "weeks", "hours", "minutes", "seconds"]
        if unit.lower() not in valid_units:
            unit = "auto"

        if unit.lower() == "auto":
            detailed, simplified = format_duration_human(total_seconds)
            result_lines.append(f"Distance: {detailed}")
            result_lines.append(f"Human readable: {simplified}")
        else:
            formatted_unit = format_duration_by_unit(total_seconds, unit.lower())
            result_lines.append(f"Distance: {formatted_unit}")

        result_lines.append(f"Direction: {direction}")

        # Add date details section
        result_lines.append("")

        # Format the from/to dates for display
        from_display = from_dt.strftime("%Y-%m-%d %H:%M:%S")
        to_display = to_dt.strftime("%Y-%m-%d %H:%M:%S")

        result_lines.append(f"From: {from_display}")
        result_lines.append(f"To: {to_display}")

        # Add location info if provided
        if tz_obj and location_name:
            result_lines.append(f"Location: {location_name}")

        # Add UTC reference
        result_lines.append("")
        result_lines.append("UTC Reference:")
        from_utc = from_dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        to_utc = to_dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        result_lines.append(f"  From: {from_utc} UTC")
        result_lines.append(f"  To: {to_utc} UTC")

    # Add NTP fallback notice if applicable
    if (from_is_now or to_is_now) and not is_ntp:
        result_lines.append("")
        result_lines.append("(Note: NTP unavailable, using local server time)")

    return "\n".join(result_lines)


# Holiday tool result functions


def get_holidays_result(
    country: str,
    year: Optional[int] = None,
    include_school_holidays: bool = False
) -> str:
    """
    Generate the result string for get_holidays tool.

    :param country: Country name or ISO code (e.g., "Poland", "PL").
    :param year: Year to fetch holidays for (defaults to current year).
    :param include_school_holidays: Whether to include school holiday periods.
    :return: Formatted string with holiday information.
    """
    # Resolve country code
    country_code = resolve_country_code(country)
    if not country_code:
        return (
            f'Could not resolve country "{country}". '
            'Please use an ISO country code (e.g., "PL", "DE", "US") '
            'or full country name (e.g., "Poland", "Germany").'
        )

    # Get country name for display
    try:
        country_info = pycountry.countries.get(alpha_2=country_code)
        country_name = country_info.name if country_info else country_code
    except (KeyError, LookupError):
        country_name = country_code

    # Determine year (use NTP time for accuracy)
    if year is None:
        ntp_time, _ = get_ntp_datetime()
        year = ntp_time.year

    result_lines = []

    # Fetch public holidays
    # Try Nager.Date first, fallback to OpenHolidaysAPI
    public_holidays = fetch_public_holidays_nager(country_code, year)
    data_source = "Nager.Date"

    if not public_holidays:
        # Try OpenHolidaysAPI as fallback
        if country_code in OPENHOLIDAYS_SUPPORTED_COUNTRIES:
            public_holidays = fetch_public_holidays_openholidays(country_code, year)
            data_source = "OpenHolidaysAPI"

    if public_holidays:
        result_lines.append(f"Public Holidays in {country_name} ({year}):")
        for h in public_holidays:
            local_name = h.get("local_name", "")
            name = h.get("name", "")
            date = h.get("date", "")

            # Format: "- 2026-01-01: New Year's Day (Nowy Rok)"
            if local_name and local_name != name:
                result_lines.append(f"- {date}: {name} ({local_name})")
            else:
                result_lines.append(f"- {date}: {name}")
    else:
        result_lines.append(f"No public holiday data available for {country_name} ({year}).")
        result_lines.append(
            "This may be because the country is not supported or the API is unavailable."
        )

    # Fetch school holidays if requested
    if include_school_holidays:
        result_lines.append("")

        if country_code in OPENHOLIDAYS_SUPPORTED_COUNTRIES:
            school_holidays = fetch_school_holidays_openholidays(country_code, year)

            if school_holidays:
                result_lines.append(f"School Holidays in {country_name} ({year}):")

                for h in school_holidays:
                    start = h.get("start_date", "")
                    end = h.get("end_date", "")
                    name = h.get("name", "Unknown")
                    regions = h.get("regions", [])
                    is_nationwide = h.get("is_nationwide", False)

                    if is_nationwide:
                        result_lines.append(f"- {start} to {end}: {name} (nationwide)")
                    elif regions:
                        # Show region names
                        region_str = ", ".join(regions)
                        result_lines.append(f"- {start} to {end}: {name} [{region_str}]")
                    else:
                        result_lines.append(f"- {start} to {end}: {name}")

                result_lines.append("")
                result_lines.append("(Note: School holiday dates may vary by region)")
            else:
                result_lines.append(
                    f"No school holiday data available for {country_name} ({year})."
                )
        else:
            result_lines.append(
                f"School holiday data is not available for {country_name}. "
                f"Only {len(OPENHOLIDAYS_SUPPORTED_COUNTRIES)} countries are supported "
                "for school holidays (mostly European countries)."
            )

    return "\n".join(result_lines)


def is_holiday_result(
    country: str = "",
    date: Optional[str] = None,
    city: str = ""
) -> str:
    """
    Check if a specific date is a holiday in a given country or city.

    :param country: Country name or ISO code (e.g., "Poland", "PL").
    :param date: Date to check in ISO format (YYYY-MM-DD). Defaults to today.
    :param city: City name (e.g., "Warsaw", "Krakow"). If provided, extracts
                 country and subdivision for region-specific holiday info.
    :return: Formatted string indicating if the date is a holiday.
    """
    country_code = None
    country_name = None
    subdivision_name = None
    subdivision_code = None
    location_display = None

    # Priority: city parameter takes precedence for detailed location info
    if city.strip():
        geo_result = geocode_location_detailed(city.strip())
        if geo_result:
            country_code, subdivision_name, location_display = geo_result
            # Try to find subdivision code for filtering school holidays
            if subdivision_name and country_code:
                subdivision_code = find_subdivision_code(country_code, subdivision_name)
        else:
            return (
                f'Could not resolve city "{city}". '
                'Try a major city name or use the country parameter instead.'
            )

    # Fall back to country parameter if no city or city didn't provide country
    if not country_code and country.strip():
        country_code = resolve_country_code(country)
        if not country_code:
            return (
                f'Could not resolve country "{country}". '
                'Please use an ISO country code (e.g., "PL", "DE", "US") '
                'or full country name (e.g., "Poland", "Germany").'
            )

    # Must have at least country or city
    if not country_code:
        return (
            'Please provide either a country (e.g., "Poland", "PL") '
            'or a city (e.g., "Warsaw", "Berlin").'
        )

    # Get country name for display
    if not country_name:
        try:
            country_info = pycountry.countries.get(alpha_2=country_code)
            country_name = country_info.name if country_info else country_code
        except (KeyError, LookupError):
            country_name = country_code

    # Parse date (default to today via NTP)
    ntp_time, _ = get_ntp_datetime()

    if date:
        date = date.strip()
        try:
            check_date = datetime.fromisoformat(date).date()
        except ValueError:
            return (
                f'Could not parse date "{date}". '
                'Please use ISO format: YYYY-MM-DD (e.g., "2026-01-01").'
            )
    else:
        check_date = ntp_time.date()

    check_date_str = check_date.isoformat()
    year = check_date.year

    # Fetch public holidays
    public_holidays = fetch_public_holidays_nager(country_code, year)
    if not public_holidays and country_code in OPENHOLIDAYS_SUPPORTED_COUNTRIES:
        public_holidays = fetch_public_holidays_openholidays(country_code, year)

    # Check for public holiday match
    matching_holidays = []
    for h in public_holidays:
        if h.get("date") == check_date_str:
            name = h.get("name", "Unknown")
            local_name = h.get("local_name", "")
            if local_name and local_name != name:
                matching_holidays.append(f"{name} ({local_name})")
            else:
                matching_holidays.append(name)

    # Check for school holiday match (if country supported)
    school_holiday_matches = []
    if country_code in OPENHOLIDAYS_SUPPORTED_COUNTRIES:
        school_holidays = fetch_school_holidays_openholidays(country_code, year)
        for h in school_holidays:
            start_str = h.get("start_date", "")
            end_str = h.get("end_date", "")
            try:
                start_date = datetime.fromisoformat(start_str).date()
                end_date = datetime.fromisoformat(end_str).date()
                if start_date <= check_date <= end_date:
                    name = h.get("name", "School Holiday")
                    regions = h.get("regions", [])
                    is_nationwide = h.get("is_nationwide", False)

                    # If we have subdivision info, filter to matching region
                    if subdivision_name and not is_nationwide:
                        # Check if this holiday applies to the user's region
                        applies_to_region = False
                        for region in regions:
                            # Match by region name (case-insensitive partial match)
                            if (subdivision_name.lower() in region.lower() or
                                    region.lower() in subdivision_name.lower()):
                                applies_to_region = True
                                break

                        if not applies_to_region:
                            continue  # Skip holidays not affecting user's region

                    # Format the match
                    if is_nationwide:
                        match_text = f"{name} (nationwide)"
                    elif subdivision_name and regions:
                        # Show that this holiday applies to the user's region
                        match_text = f"{name} (affects {subdivision_name})"
                    elif regions:
                        region_str = ", ".join(regions[:3])
                        if len(regions) > 3:
                            region_str += f" and {len(regions) - 3} more regions"
                        match_text = f"{name} [{region_str}]"
                    else:
                        match_text = name

                    school_holiday_matches.append(match_text)
            except ValueError:
                continue

    # Build response
    result_lines = []

    # Show location if city was used
    display_location = location_display if location_display else country_name

    if matching_holidays:
        result_lines.append(f"Yes, {check_date_str} is a holiday in {display_location}.")
        result_lines.append("")
        result_lines.append("Public Holiday(s):")
        for holiday in matching_holidays:
            result_lines.append(f"  - {holiday}")
    else:
        result_lines.append(
            f"No, {check_date_str} is not a public holiday in {display_location}."
        )

    if school_holiday_matches:
        if not matching_holidays:
            result_lines = []
            result_lines.append(
                f"{check_date_str} is during a school holiday in {display_location}."
            )
        result_lines.append("")
        if len(school_holiday_matches) == 1:
            result_lines.append(f"School Holiday: {school_holiday_matches[0]}")
        else:
            result_lines.append("School Holidays:")
            for match in school_holiday_matches:
                result_lines.append(f"  - {match}")

    # Add region context if city was specified
    if city.strip() and subdivision_name:
        result_lines.append("")
        result_lines.append(f"Region: {subdivision_name}, {country_name}")

    return "\n".join(result_lines)

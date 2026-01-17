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

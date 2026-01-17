"""
Core functionality shared between local and web MCP timeserver variants.

This module contains:
- NTP time fetching
- Calendar formatting functions
- Shared tool implementation logic
"""
from datetime import datetime, UTC
import ntplib
from hijridate import Gregorian
from japanera import EraDateTime
from pyluach import dates as hebrew_dates
from persiantools.jdatetime import JalaliDateTime


# Default NTP server
DEFAULT_NTP_SERVER = 'pool.ntp.org'


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


def current_time_result(calendar: str = "") -> str:
    """
    Generate the result string for get_current_time tool.

    :param calendar: Comma-separated list of calendar formats to include.
    :return: Formatted time string with optional calendar conversions.
    """
    ntp_time, is_ntp = get_ntp_datetime()
    formatted_time = ntp_time.strftime("%Y-%m-%d %H:%M:%S")
    day_of_week = ntp_time.strftime("%A")
    gregorian_date = ntp_time.strftime("%Y-%m-%d")

    # Build base response
    result_lines = [
        f"UTC Time: {formatted_time}",
        f"Day: {day_of_week}",
    ]

    # Process requested calendars if any
    warnings = []
    calendar_sections = []

    if calendar.strip():
        # Add the Gregorian date line when calendars are requested
        result_lines.append(f"Date: {gregorian_date} (Gregorian)")

        requested = [c.strip().lower() for c in calendar.split(",")]
        for cal_name in requested:
            if not cal_name:
                continue
            if cal_name in CALENDAR_FORMATTERS:
                calendar_sections.append(CALENDAR_FORMATTERS[cal_name](ntp_time))
            else:
                warnings.append(f"(Note: Unknown calendar format ignored: {cal_name})")

    # Build final result
    result = "\n".join(result_lines)

    if calendar_sections:
        result += "\n\n" + "\n\n".join(calendar_sections)

    if warnings:
        result += "\n\n" + "\n".join(warnings)

    # Add fallback notice if NTP was unavailable
    if not is_ntp:
        result += "\n(Note: NTP unavailable, using local server time)"

    return result

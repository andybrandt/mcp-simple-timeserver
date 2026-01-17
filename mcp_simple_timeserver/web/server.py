from datetime import date, datetime, UTC
import ntplib
from fastmcp import FastMCP  # FastMCP 2.0 import
from hijridate import Gregorian
from japanera import EraDateTime
from pyluach import dates as hebrew_dates
from persiantools.jdatetime import JalaliDateTime

# Create the FastMCP app with web-specific settings
app = FastMCP(
    "mcp-simple-timeserver", 
    stateless_http=True,
    host="0.0.0.0",  # Listen on all interfaces inside the container
    port=8000,
    auth=None  # Explicitly disable authentication
)

DEFAULT_NTP_SERVER = 'pool.ntp.org'


def _get_ntp_datetime(server: str = DEFAULT_NTP_SERVER) -> tuple[datetime, bool]:
    """
    Fetches accurate UTC time from an NTP server.
    Returns a tuple of (datetime, is_ntp_time).
    If NTP fails, falls back to local time with is_ntp_time=False.
    """
    try:
        ntp_client = ntplib.NTPClient()
        response = ntp_client.request(server, version=3)
        return datetime.fromtimestamp(response.tx_time, tz=UTC), True
    except (ntplib.NTPException, OSError):
        # Catches NTP errors, socket timeouts, and network errors
        return datetime.now(tz=UTC), False


# Helper functions for calendar formatting in get_current_time tool

def _format_unix(ntp_time: datetime) -> str:
    """Format time as Unix timestamp."""
    timestamp = int(ntp_time.timestamp())
    return f"--- Unix Timestamp ---\n{timestamp}"


def _format_isodate(ntp_time: datetime) -> str:
    """Format time as ISO 8601 week date."""
    iso_week_date = ntp_time.strftime("%G-W%V-%u")
    return f"--- ISO Week Date ---\n{iso_week_date}"


def _calendar_hijri(ntp_time: datetime) -> str:
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


def _calendar_japanese(ntp_time: datetime) -> str:
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


def _calendar_persian(ntp_time: datetime) -> str:
    """Format time in Persian (Jalali) calendar (both English and Farsi)."""
    jalali_dt = JalaliDateTime(ntp_time)
    english_formatted = jalali_dt.strftime("%A %d %B %Y", locale="en")
    farsi_formatted = jalali_dt.strftime("%A %d %B %Y", locale="fa")
    return (
        f"--- Persian Calendar ---\n"
        f"English: {english_formatted}\n"
        f"Farsi: {farsi_formatted}"
    )


def _calendar_hebrew(ntp_time: datetime) -> str:
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
    "unix": _format_unix,
    "isodate": _format_isodate,
    "hijri": _calendar_hijri,
    "japanese": _calendar_japanese,
    "persian": _calendar_persian,
    "hebrew": _calendar_hebrew,
}


@app.tool(
    annotations = {
        "title": "Get Local Time and Timezone for the Server Hosting this Tool",
        "readOnlyHint": True
    }
)
def get_server_time() -> str:
    """
    Returns the current local time and timezone from the server hosting this tool.
    Note: This is the server's time, which may be different from the user's local time.
    """
    local_time = datetime.now()
    timezone = str(local_time.astimezone().tzinfo)
    formatted_time = local_time.strftime("%Y-%m-%d %H:%M:%S")
    day_of_week = local_time.strftime("%A")
    return f"Current Server Time: {formatted_time}\nDay: {day_of_week}\nTimezone: {timezone}"

@app.tool(
    annotations={
        "title": "Get UTC Time from an NTP Server",
        "readOnlyHint": True
    }
)
def get_utc(server: str = DEFAULT_NTP_SERVER) -> str:
    """
    Returns accurate UTC time from an NTP server.
    This provides a universal time reference regardless of local timezone.
    
    :param server: NTP server address (default: pool.ntp.org)
    """
    utc_time, is_ntp = _get_ntp_datetime(server)
    formatted_time = utc_time.strftime("%Y-%m-%d %H:%M:%S")
    day_of_week = utc_time.strftime("%A")
    fallback_notice = "" if is_ntp else "\n(Note: NTP unavailable, using local server time)"
    return f"Current UTC Time from {server}: {formatted_time}\nDay: {day_of_week}{fallback_notice}"


@app.tool(
    annotations={
        "title": "Get Current Time with Optional Calendar Systems and Formats",
        "readOnlyHint": True
    }
)
def get_current_time(calendar: str = "") -> str:
    """
    Returns the current UTC time with Gregorian date, and optionally converts to
    additional calendar systems or formats.

    The response ALWAYS includes:
    - UTC time (YYYY-MM-DD HH:MM:SS format)
    - Gregorian date with day of week
    - Timezone name (currently always "UTC")

    :param calendar: Comma-separated list of additional calendars/formats to include.
        Valid values (case-insensitive):
        - "unix" - Unix timestamp (seconds since 1970-01-01)
        - "isodate" - ISO 8601 week date (YYYY-Www-D)
        - "hijri" - Islamic/Hijri lunar calendar
        - "japanese" - Japanese Era calendar (returns BOTH English and Kanji)
        - "persian" - Persian/Jalali calendar (returns BOTH English and Farsi)
        - "hebrew" - Hebrew/Jewish calendar (returns BOTH English and Hebrew script)

        Example: "unix,hijri" returns UTC time plus Unix timestamp and Hijri date.
        Leave empty to get only UTC/Gregorian time.
        Invalid calendar names are reported but do not cause errors.

    Uses accurate time from NTP server when available.
    """
    ntp_time, is_ntp = _get_ntp_datetime()
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


if __name__ == "__main__":
    # Run the server with streamable-http transport
    app.run(transport="streamable-http")
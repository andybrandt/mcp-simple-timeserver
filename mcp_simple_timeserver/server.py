from datetime import date, datetime, UTC
import ntplib
from fastmcp import FastMCP  # FastMCP 2.0 import
from hijridate import Gregorian
from japanera import EraDateTime
from pyluach import dates as hebrew_dates
from persiantools.jdatetime import JalaliDateTime

# Default NTP server
DEFAULT_NTP_SERVER = 'pool.ntp.org'

app = FastMCP("mcp-simple-timeserver")


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


# Note: in this context the docstring are meant for the client AI to understand the tools and their purpose.

@app.tool(
    annotations = {
        "title": "Get Local Time and Timezone",
        "readOnlyHint": True
    }
)
def get_local_time() -> str:
    """
    Returns the current local time and timezone information from your local machine.
    This helps you understand what time it is for the user you're assisting.
    """
    local_time = datetime.now()
    timezone = str(local_time.astimezone().tzinfo)
    formatted_time = local_time.strftime("%Y-%m-%d %H:%M:%S")
    day_of_week = local_time.strftime("%A")
    return f"Current Time: {formatted_time}\nDay: {day_of_week}\nTimezone: {timezone}"

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
        "title": "Get current date as ISO Week Date",
        "readOnlyHint": True
    }
)
def get_iso_week_date() -> str:
    """
    Returns the current date in ISO 8601 week date format (YYYY-Www-D).
    Uses accurate time from NTP server.
    Useful for weekly planning and scheduling contexts.
    """
    ntp_time, is_ntp = _get_ntp_datetime()
    iso_week_date = ntp_time.strftime("%G-W%V-%u")
    fallback_notice = "" if is_ntp else "\n(Note: NTP unavailable, using local server time)"
    return f"ISO Week Date: {iso_week_date}{fallback_notice}"

@app.tool(
    annotations={
        "title": "Get current time as Unix Timestamp",
        "readOnlyHint": True
    }
)
def get_unix_timestamp() -> str:
    """
    Returns the current time as a Unix timestamp (POSIX time).
    Uses accurate time from NTP server.
    This is the number of seconds since January 1, 1970 (UTC).
    Useful for logging, APIs, and cross-system time synchronization.
    """
    ntp_time, is_ntp = _get_ntp_datetime()
    timestamp = ntp_time.timestamp()
    fallback_notice = "" if is_ntp else "\n(Note: NTP unavailable, using local server time)"
    return f"Unix Timestamp: {int(timestamp)}{fallback_notice}"

@app.tool(
    annotations={
        "title": "Get current date and time in Hijri (Islamic) calendar",
        "readOnlyHint": True
    }
)
def get_hijri_date() -> str:
    """
    Returns the current date and time in the Islamic (Hijri) lunar calendar.
    Uses accurate time from NTP server.
    Useful for Islamic religious observances and cultural contexts.
    """
    ntp_time, is_ntp = _get_ntp_datetime()
    hijri = Gregorian.fromdate(ntp_time.date()).to_hijri()
    hijri_formatted = hijri.isoformat()
    current_time = ntp_time.strftime("%H:%M:%S")
    month_name = hijri.month_name()
    day_name = hijri.day_name()
    notation = hijri.notation()
    fallback_notice = "" if is_ntp else "\n(Note: NTP unavailable, using local server time)"
    return f"Hijri Date: {hijri_formatted} {notation}\nTime: {current_time}\nMonth: {month_name}\nDay: {day_name}{fallback_notice}"

@app.tool(
    annotations={
        "title": "Get current date and time in Japanese Era calendar",
        "readOnlyHint": True
    }
)
def get_japanese_era_date(language: str = "en") -> str:
    """
    Returns the current date and time in the Japanese Era (Nengo) calendar.
    Uses accurate time from NTP server.
    Useful for Japanese cultural and official document contexts.
    
    :param language: Output language - "en" for English, "ja" for Kanji (default: en)
    """
    ntp_time, is_ntp = _get_ntp_datetime()
    era_datetime = EraDateTime.from_datetime(ntp_time)
    
    if language == "ja":
        # Format: 令和7年01月15日 14時
        formatted = era_datetime.strftime("%-K%-y年%m月%d日 %H時")
        era_name = era_datetime.era.kanji
    else:
        # Format: Reiwa 7, January 15, 14:00
        formatted = era_datetime.strftime("%-E %-Y, %B %d, %H:%M")
        era_name = era_datetime.era.english
    
    fallback_notice = "" if is_ntp else "\n(Note: NTP unavailable, using local server time)"
    return f"Japanese Era Date: {formatted}\nEra: {era_name}{fallback_notice}"

@app.tool(
    annotations={
        "title": "Get current date and time in Hebrew (Jewish) calendar",
        "readOnlyHint": True
    }
)
def get_hebrew_date(language: str = "en") -> str:
    """
    Returns the current date and time in the Hebrew (Jewish) calendar.
    Uses accurate time from NTP server.
    Useful for Jewish religious observances and cultural contexts.
    
    :param language: Output language - "en" for English, "he" for Hebrew (default: en)
    """
    ntp_time, is_ntp = _get_ntp_datetime()
    # Convert NTP date to Hebrew date via GregorianDate
    gregorian_date = hebrew_dates.GregorianDate(
        ntp_time.year, ntp_time.month, ntp_time.day
    )
    hebrew_date = gregorian_date.to_heb()
    current_time = ntp_time.strftime("%H:%M:%S")
    
    if language == "he":
        formatted = hebrew_date.hebrew_date_string()
    else:
        formatted = f"{hebrew_date.day} {hebrew_date.month_name()} {hebrew_date.year}"
    
    # Check for holiday
    holiday = hebrew_date.holiday(hebrew=(language == "he"))
    holiday_line = f"\nHoliday: {holiday}" if holiday else ""
    fallback_notice = "" if is_ntp else "\n(Note: NTP unavailable, using local server time)"
    
    return f"Hebrew Date: {formatted}\nTime: {current_time}{holiday_line}{fallback_notice}"

@app.tool(
    annotations={
        "title": "Get current date and time in Persian (Jalali) calendar",
        "readOnlyHint": True
    }
)
def get_persian_date(language: str = "en") -> str:
    """
    Returns the current date and time in the Persian (Jalali/Shamsi) calendar.
    Uses accurate time from NTP server.
    Useful for Iranian cultural and official contexts.
    
    :param language: Output language - "en" for English, "fa" for Farsi (default: en)
    """
    ntp_time, is_ntp = _get_ntp_datetime()
    jalali_dt = JalaliDateTime(ntp_time)
    current_time = ntp_time.strftime("%H:%M:%S")
    
    if language == "fa":
        formatted = jalali_dt.strftime("%A %d %B %Y", locale="fa")  # Persian/Farsi names
    else:
        formatted = jalali_dt.strftime("%A %d %B %Y", locale="en")  # English names
    
    fallback_notice = "" if is_ntp else "\n(Note: NTP unavailable, using local server time)"
    return f"Persian Date: {formatted}\nTime: {current_time}{fallback_notice}"

if __name__ == "__main__":
    app.run()
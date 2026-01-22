"""
MCP Simple Timeserver - Local (stdio) variant.

This server provides time-related tools to AI assistants via the
Model Context Protocol (MCP) using stdio transport.
"""
from datetime import datetime
from importlib.metadata import version

from fastmcp import FastMCP

from .core import (
    DEFAULT_NTP_SERVER,
    utc_time_result,
    current_time_result,
    time_distance_result,
)


# Get package version dynamically from pyproject.toml via importlib.metadata
_version = version("mcp-simple-timeserver")

app = FastMCP("mcp-simple-timeserver", version=_version)


# Note: in this context the docstrings are meant for the client AI
# to understand the tools and their purpose.

@app.tool(
    annotations={
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
    return utc_time_result(server)


@app.tool(
    annotations={
        "title": "Get Current Time with Optional Location and Calendar Systems",
        "readOnlyHint": True
    }
)
def get_current_time(
    calendar: str = "",
    timezone: str = "",
    country: str = "",
    city: str = ""
) -> str:
    """
    Returns current time, optionally localized to a specific location or timezone,
    with optional conversion to additional calendar systems.

    LOCATION PARAMETERS (use one, priority: timezone > city > country):

    :param city: City name (PRIMARY USE CASE). Examples: "Warsaw", "Tokyo", "New York"
        Resolves city to timezone automatically. Best for most queries.

    :param country: Country name or code. Examples: "Poland", "JP", "United States"
        Falls back to capital/major city timezone. Use when city is unknown.

    :param timezone: Direct IANA timezone or UTC offset. Examples: "Europe/Warsaw", "+05:30"
        Escape hatch for precise control. Use when you know the exact timezone.

    When a location is provided, the response includes:
    - Local time at that location
    - Timezone name and abbreviation (e.g., "Europe/Warsaw (CET)")
    - UTC offset (e.g., "+01:00")
    - DST status (Yes/No)
    - UTC time for reference

    When NO location is provided, returns UTC time only (original behavior).

    CALENDAR PARAMETER:

    :param calendar: Comma-separated list of additional calendars/formats.
        Valid values (case-insensitive):
        - "unix" - Unix timestamp (seconds since 1970-01-01)
        - "isodate" - ISO 8601 week date (YYYY-Www-D)
        - "hijri" - Islamic/Hijri lunar calendar
        - "japanese" - Japanese Era calendar (English and Kanji)
        - "persian" - Persian/Jalali calendar (English and Farsi)
        - "hebrew" - Hebrew/Jewish calendar (English and Hebrew script)

        Calendars are calculated for the LOCAL time when location is specified.

    EXAMPLES:
    - get_current_time(city="Warsaw") - Time in Warsaw with timezone info
    - get_current_time(city="Tokyo", calendar="japanese") - Tokyo time with Japanese calendar
    - get_current_time(timezone="+05:30") - Time at UTC+5:30 offset
    - get_current_time() - UTC time only (no location)

    Uses accurate time from NTP server when available.
    Invalid locations fall back to UTC with a helpful message.
    """
    return current_time_result(calendar, timezone, country, city)


@app.tool(
    annotations={
        "title": "Calculate Time/Date Distance",
        "readOnlyHint": True
    }
)
def calculate_time_distance(
    from_date: str = "now",
    to_date: str = "now",
    unit: str = "auto",
    timezone: str = "",
    city: str = "",
    country: str = ""
) -> str:
    """
    Calculate the duration/distance between two dates or datetimes.
    Use this tool for countdowns, elapsed time calculations, or scheduling queries.

    :param from_date: Start date in ISO 8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS) or "now".
        Examples: "2025-01-15", "2025-01-15T09:30:00", "now"

    :param to_date: End date in ISO 8601 format or "now".
        Examples: "2025-12-31", "2025-06-01T17:00:00", "now"

    :param unit: Output format for the distance. Options:
        - "auto" (default) - Human-readable breakdown (e.g., "15 days, 3 hours, 45 minutes")
        - "days" - Decimal days (e.g., "15.50 days")
        - "weeks" - Decimal weeks (e.g., "2.21 weeks")
        - "hours" - Decimal hours (e.g., "372.00 hours")
        - "minutes" - Decimal minutes (e.g., "22320.00 minutes")
        - "seconds" - Total seconds (e.g., "1339200 seconds")

    LOCATION PARAMETERS (optional, same as get_current_time):

    :param city: City name for timezone context. Examples: "Warsaw", "Tokyo", "New York"
    :param country: Country name or code. Examples: "Poland", "JP"
    :param timezone: Direct IANA timezone or UTC offset. Examples: "Europe/Warsaw", "+05:30"

    Location affects how dates without explicit timezone are interpreted.
    Priority: timezone > city > country. If none provided, UTC is used.

    OUTPUT FORMAT:
    - Distance: The calculated duration
    - Human readable: Simplified summary (when unit="auto")
    - Direction: "future" if to_date > from_date, "past" if to_date < from_date
    - From/To: The parsed datetime values
    - UTC Reference: Both times converted to UTC

    COMMON USE CASES:
    - "How many days until Dec 31?" → from_date="now", to_date="2025-12-31"
    - "How long since Jan 1?" → from_date="2025-01-01", to_date="now"
    - "Duration between two dates" → from_date="2025-01-01", to_date="2025-03-15"

    NOTE: If both parameters are the same (e.g., both "now"), returns an error message.
    Uses accurate NTP time when "now" is specified.
    """
    return time_distance_result(from_date, to_date, unit, timezone, country, city)


if __name__ == "__main__":
    app.run()

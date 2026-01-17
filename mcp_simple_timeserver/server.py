"""
MCP Simple Timeserver - Local (stdio) variant.

This server provides time-related tools to AI assistants via the
Model Context Protocol (MCP) using stdio transport.
"""
from datetime import datetime
from fastmcp import FastMCP

from .core import (
    DEFAULT_NTP_SERVER,
    utc_time_result,
    current_time_result,
)


app = FastMCP("mcp-simple-timeserver")


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
    return current_time_result(calendar)


if __name__ == "__main__":
    app.run()

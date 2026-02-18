"""
MCP Simple Timeserver - Web (HTTP) variant.

This server provides time-related tools to AI assistants via the
Model Context Protocol (MCP) using streamable HTTP transport.
Designed for network deployment behind a reverse proxy.
"""
from datetime import datetime
from importlib.metadata import version

from fastmcp import FastMCP

from ..core import (
    DEFAULT_NTP_SERVER,
    utc_time_result,
    current_time_result,
    time_distance_result,
    get_holidays_result,
    is_holiday_result,
)


# Get package version dynamically from pyproject.toml via importlib.metadata
_version = version("mcp-simple-timeserver")

# Create the FastMCP app with web-specific settings
# Note: host and port moved to run() per FastMCP 2.x deprecation.
# stateless_http remains here as run() doesn't support it yet (see FastMCP issue #996).
app = FastMCP(
    "mcp-simple-timeserver",
    version=_version,
    stateless_http=False,
    auth=None  # Explicitly disable authentication
)


@app.tool(
    annotations={
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
    country: str = "",
    business_days: bool = False,
    exclude_holidays: bool = False
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

    BUSINESS DAYS MODE (optional):

    :param business_days: Count only business days (Mon-Fri), excluding weekends. Default: False.
        When True, returns business day count instead of elapsed-time duration.
        Time-of-day is ignored; dates are counted as full days (inclusive endpoints).
        The `unit` parameter is ignored in this mode.

    :param exclude_holidays: Also exclude public holidays. Default: False.
        Only effective when business_days=True.
        Requires country or city parameter to determine which holidays to exclude.
        If country cannot be determined, proceeds with weekend-only exclusion.

    Example: "How many business days until project deadline?"
        from_date="now", to_date="2026-03-15", business_days=True, country="Poland"

    COMMON USE CASES:
    - "How many days until Dec 31?" → from_date="now", to_date="2025-12-31"
    - "How long since Jan 1?" → from_date="2025-01-01", to_date="now"
    - "Duration between two dates" → from_date="2025-01-01", to_date="2025-03-15"

    NOTE: If both parameters are the same (e.g., both "now"), returns an error message.
    Uses accurate NTP time when "now" is specified.
    """
    return time_distance_result(
        from_date,
        to_date,
        unit,
        timezone,
        country,
        city,
        business_days,
        exclude_holidays
    )


@app.tool(
    annotations={
        "title": "Get Holidays for a Country",
        "readOnlyHint": True
    }
)
def get_holidays(
    country: str,
    year: int = 0,
    include_school_holidays: bool = False
) -> str:
    """
    Get a list of public holidays (and optionally school holidays) for a country and year.
    Use this tool when the user asks about holidays, days off, or vacation periods.

    :param country: Country name or ISO code (required).
        Examples: "Poland", "PL", "United States", "US", "Germany", "DE"
        Supports common aliases like "UK" for United Kingdom.

    :param year: Year to get holidays for (optional).
        Defaults to current year if not specified or 0.
        Examples: 2026, 2027

    :param include_school_holidays: Whether to include school vacation periods (optional).
        Default is False. Set to True to see school holidays.
        School holidays are only available for ~36 countries (mostly European).
        School holidays may vary by region (e.g., different dates for different states/provinces).

    OUTPUT FORMAT:
    - Public holidays: Date, name (with local name if different)
    - School holidays (if requested): Date range, name, regions affected

    EXAMPLES:
    - get_holidays(country="Poland") - All public holidays in Poland this year
    - get_holidays(country="DE", year=2026) - German holidays for 2026
    - get_holidays(country="Poland", include_school_holidays=True) - Polish holidays + school vacations

    NOTE: Public holiday data is available for ~119 countries.
    School holiday data is available for ~36 countries (mostly European).
    """
    # Convert year=0 to None for the core function (means "use current year")
    actual_year = year if year > 0 else None
    return get_holidays_result(country, actual_year, include_school_holidays)


@app.tool(
    annotations={
        "title": "Check if Date is a Holiday",
        "readOnlyHint": True
    }
)
def is_holiday(
    country: str = "",
    date: str = "",
    city: str = ""
) -> str:
    """
    Check if a specific date is a holiday in a given country or city.
    Use this tool to quickly verify if a particular day is a public or school holiday.

    LOCATION PARAMETERS (use at least one):

    :param country: Country name or ISO code.
        Examples: "Poland", "PL", "United States", "US"

    :param city: City name (PRIMARY USE CASE for regional holidays).
        Examples: "Warsaw", "Krakow", "Berlin", "Munich"
        When specified, automatically detects country and region for accurate
        school holiday filtering (e.g., school holidays vary by Polish voivodeship).

    :param date: Date to check in ISO format YYYY-MM-DD (optional).
        Defaults to today if not specified.
        Examples: "2026-01-01", "2026-12-25"

    OUTPUT FORMAT:
    - Yes/No indication if the date is a public holiday
    - Holiday name(s) if it is a holiday
    - School holiday information filtered to the specific region (if city provided)

    EXAMPLES:
    - is_holiday(city="Warsaw", date="2026-01-19") - Check school holidays in Warsaw
    - is_holiday(city="Krakow") - Check if today is a holiday in Krakow
    - is_holiday(country="Poland", date="2026-01-01") - Check New Year's Day in Poland
    - is_holiday(country="Germany", date="2026-12-25") - Check Christmas Day in Germany

    NOTE: Using city parameter provides region-specific school holiday info.
    School holidays vary by region in many countries (e.g., Polish voivodeships,
    German Bundesländer). Only ~36 countries have school holiday data available.
    """
    # Convert empty strings to appropriate values for the core function
    actual_date = date if date else None
    return is_holiday_result(country, actual_date, city)


if __name__ == "__main__":
    # Run the server with streamable-http transport
    # Host 0.0.0.0 to listen on all interfaces inside the container
    app.run(transport="streamable-http", host="0.0.0.0", port=8000)

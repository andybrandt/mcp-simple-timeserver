from datetime import datetime, UTC
import ntplib
from fastmcp import FastMCP  # FastMCP 2.0 import

# Default NTP server
DEFAULT_NTP_SERVER = 'pool.ntp.org'

app = FastMCP("mcp-simple-timeserver")

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
    annotations = {
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
    try:
        ntp_client = ntplib.NTPClient()
        response = ntp_client.request(server, version=3)
        utc_time = datetime.fromtimestamp(response.tx_time, tz=UTC)
        formatted_time = utc_time.strftime("%Y-%m-%d %H:%M:%S")
        day_of_week = utc_time.strftime("%A")
        return f"Current UTC Time from {server}: {formatted_time}\nDay: {day_of_week}"
    except ntplib.NTPException as e:
        return f"Error getting NTP time: {str(e)}"

@app.tool(
    annotations={
        "title": "Get current date as ISO Week Date",
        "readOnlyHint": True
    }
)
def get_iso_week_date() -> str:
    """
    Returns the current date in ISO 8601 week date format (YYYY-Www-D).
    Useful for weekly planning and scheduling contexts.
    """
    local_time = datetime.now()
    iso_week_date = local_time.strftime("%G-W%V-%u")
    return f"ISO Week Date: {iso_week_date}"

@app.tool(
    annotations={
        "title": "Get current time as Unix Timestamp",
        "readOnlyHint": True
    }
)
def get_unix_timestamp() -> str:
    """
    Returns the current time as a Unix timestamp (POSIX time).
    This is the number of seconds since January 1, 1970 (UTC).
    Useful for logging, APIs, and cross-system time synchronization.
    """
    timestamp = datetime.now().timestamp()
    return f"Unix Timestamp: {int(timestamp)}"

if __name__ == "__main__":
    app.run()
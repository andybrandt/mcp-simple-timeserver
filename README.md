[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/andybrandt-mcp-simple-timeserver-badge.png)](https://mseep.ai/app/andybrandt-mcp-simple-timeserver)

# MCP Simple Timeserver
[![Trust Score](https://archestra.ai/mcp-catalog/api/badge/quality/andybrandt/mcp-simple-timeserver)](https://archestra.ai/mcp-catalog/andybrandt__mcp-simple-timeserver)
[![smithery badge](https://smithery.ai/badge/mcp-simple-timeserver)](https://smithery.ai/server/mcp-simple-timeserver)

*One of the strange design decisions Anthropic made was depriving Claude of timestamps for messages sent by the user in claude.ai or current time in general. Poor Claude can't tell what time it is! `mcp-simple-timeserver` is a simple MCP server that fixes that.*

## Available Tools

This server provides the following tools:

| Tool | Description |
|------|-------------|
| `get_local_time` | Returns the current local time, day of week, and timezone from the user's machine |
| `get_utc` | Returns accurate UTC time from an [NTP time server](https://en.wikipedia.org/wiki/Network_Time_Protocol) |
| `get_current_time` | Returns current time with optional location, timezone, and calendar conversions |
| `calculate_time_distance` | Calculates duration between two dates/times (countdowns, elapsed time) |
| `get_holidays` | Returns public holidays (and optionally school holidays) for a country |
| `is_holiday` | Checks if a specific date is a holiday in a given country or city |

All tools (except `get_local_time`) use accurate time from NTP servers. If NTP is unavailable, they gracefully fall back to local server time with a notice.

### Location Support via `get_current_time`

The `get_current_time` tool supports location parameters to get local time anywhere in the world:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `city` | City name (primary use case) | `"Warsaw"`, `"Tokyo"`, `"New York"` |
| `country` | Country name or ISO code | `"Poland"`, `"JP"`, `"United States"` |
| `timezone` | IANA timezone or UTC offset | `"Europe/Warsaw"`, `"+05:30"` |

Priority: `timezone` > `city` > `country`. When location is provided, the response includes local time, timezone info, UTC offset, and DST status.

If today is a public holiday at the specified location, it will be shown in the output.

### Calendar Support via `get_current_time`

The `get_current_time` tool also accepts an optional `calendar` parameter with a comma-separated list of calendar formats:

| Calendar | Description |
|----------|-------------|
| `unix` | Unix timestamp (seconds since 1970-01-01) |
| `isodate` | ISO 8601 week date (e.g., `2026-W03-6`) |
| `hijri` | Islamic/Hijri lunar calendar |
| `japanese` | Japanese Era calendar (returns both English and Kanji) |
| `hebrew` | Hebrew/Jewish calendar (returns both English and Hebrew, includes holidays) |
| `persian` | Persian/Jalali calendar (returns both English and Farsi) |

Example: `get_current_time(city="Tokyo", calendar="japanese")` returns Tokyo local time with Japanese Era calendar.

### Time Distance Calculation via `calculate_time_distance`

Calculate duration between two dates or times:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `from_date` | Start date (ISO 8601 or "now") | `"2025-01-15"`, `"now"` |
| `to_date` | End date (ISO 8601 or "now") | `"2025-12-31"`, `"2025-06-01T17:00:00"` |
| `unit` | Output format | `"auto"`, `"days"`, `"weeks"`, `"hours"`, `"minutes"`, `"seconds"` |

Location parameters (`city`, `country`, `timezone`) can also be used to specify timezone context.

Example: `calculate_time_distance(from_date="now", to_date="2025-12-31")` returns a countdown to New Year's Eve.

### Holiday Information via `get_holidays` and `is_holiday`

Get public and school holiday information for ~119 countries:

**`get_holidays`** parameters:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `country` | Country name or ISO code (required) | `"Poland"`, `"DE"`, `"United States"` |
| `year` | Year to get holidays for (default: current year) | `2026` |
| `include_school_holidays` | Include school vacation periods | `true` |

**`is_holiday`** parameters:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `country` | Country name or ISO code | `"Poland"`, `"US"` |
| `city` | City name for region-specific info | `"Warsaw"`, `"Munich"` |
| `date` | Date to check in ISO format (default: today) | `"2026-01-01"` |

**Regional School Holidays**: When using the `city` parameter with `is_holiday`, school holidays are filtered to show only those affecting the specific region. This is particularly useful in countries where school holidays vary by region (e.g., Polish voivodeships, German Bundesländer, Spanish autonomous communities).

Example: `is_holiday(city="Warsaw", date="2026-01-19")` returns school holiday information specific to the Mazowieckie voivodeship.

**Data Sources**:
- Public holidays: [Nager.Date API](https://date.nager.at/) (119 countries)
- School holidays: [OpenHolidaysAPI](https://openholidaysapi.org/) (36 countries, mostly European)

## Installation

### Installing via Smithery

To install Simple Timeserver for Claude Desktop automatically via [Smithery](https://smithery.ai/server/mcp-simple-timeserver):

```bash
npx -y @smithery/cli install mcp-simple-timeserver --client claude
```

### Manual Installation
First install the module using:

```bash
pip install mcp-simple-timeserver

```

Then configure in MCP client - the [Claude desktop app](https://claude.ai/download).

Under Mac OS this will look like this:

```json
"mcpServers": {
  "simple-timeserver": {
    "command": "python",
    "args": ["-m", "mcp_simple_timeserver"]
  }
}
```

Under Windows you have to check the path to your Python executable using `where python` in the `cmd` (Windows command line). 

Typical configuration would look like this:

```json
"mcpServers": {
  "simple-timeserver": {
    "command": "C:\\Users\\YOUR_USERNAME\\AppData\\Local\\Programs\\Python\\Python311\\python.exe",
    "args": ["-m", "mcp_simple_timeserver"]
  }
}
```

## Web Server Variant

This project also includes a network-hostable version that can be deployed as a standalone web server. For instructions on how to run and deploy it, please see the [Web Server Deployment Guide](WEB_DEPLOYMENT.md).

Or you can simply use my server by adding it under https://mcp.andybrandt.net/timeserver to Claude and other tools that support MCP.

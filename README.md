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
| `get_current_time` | Returns current UTC time with optional calendar conversions (see below) |

### Calendar Support via `get_current_time`

The `get_current_time` tool accepts an optional `calendar` parameter with a comma-separated list of calendar formats:

| Calendar | Description |
|----------|-------------|
| `unix` | Unix timestamp (seconds since 1970-01-01) |
| `isodate` | ISO 8601 week date (e.g., `2026-W03-6`) |
| `hijri` | Islamic/Hijri lunar calendar |
| `japanese` | Japanese Era calendar (returns both English and Kanji) |
| `hebrew` | Hebrew/Jewish calendar (returns both English and Hebrew, includes holidays) |
| `persian` | Persian/Jalali calendar (returns both English and Farsi) |

Example: `get_current_time(calendar="unix,hijri")` returns UTC time plus Unix timestamp and Hijri date.

All tools (except `get_local_time`) use accurate time from NTP servers. If NTP is unavailable, they gracefully fall back to local server time with a notice.

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

[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/andybrandt-mcp-simple-timeserver-badge.png)](https://mseep.ai/app/andybrandt-mcp-simple-timeserver)

# MCP Simple Timeserver
[![smithery badge](https://smithery.ai/badge/mcp-simple-timeserver)](https://smithery.ai/server/mcp-simple-timeserver)

*One of the strange design decisions Anthropic made was depriving Claude of timestamps for messages sent by the user or current time in general. Poor Claude can't tell what time it is! `mcp-simple-timeserver` is a simple MCP server that fixes that.*

This server provides two tools:
 - `get_time` provides the current local time and timezone information from the user's machine. This way Claude can know what time it is at the user's location. He can also calculate how much time passed since his last interaction with the user should he want to do so. 
 - `get_utc` provides current UTC time obtained from an [NTP time server](https://en.wikipedia.org/wiki/Network_Time_Protocol). 

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


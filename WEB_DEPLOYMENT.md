# Web Server Deployment Guide

This guide explains how to run the network-hostable version of the `mcp-simple-timeserver`. This version uses the MCP Streamable HTTP transport and is ideal for deployments where clients connect over a network.

## Overview

The web server is a stateless service that exposes 6 tools:

| Tool | Description |
|------|-------------|
| `get_server_time` | Returns the local time and timezone of the server machine |
| `get_utc` | Returns accurate UTC time from an NTP server |
| `get_current_time` | Returns current time with optional location, timezone, and calendar conversions |
| `calculate_time_distance` | Calculates duration between two dates/times (countdowns, elapsed time, or business-day counts) |
| `get_holidays` | Returns public holidays (and optionally school holidays) for a country |
| `is_holiday` | Checks if a specific date is a holiday in a given country or city |

All tools (except `get_server_time`) use accurate time from NTP servers with graceful fallback to local time.

The `calculate_time_distance` tool also supports `business_days` and `exclude_holidays` parameters for date-based, inclusive business-day counting. See the main [README.md](README.md) for detailed documentation of tool parameters and usage examples.

It runs using FastMCP's built-in web server (based on Uvicorn/Starlette).

## Local Development

### 1. Install Dependencies

First, ensure you have a virtual environment set up and the base dependencies installed:

```bash
python3 -m venv venv
venv/bin/pip install -e .
```

The web server dependencies (`uvicorn`, `starlette`) are included by the core `mcp` package.

### 2. Run the Server

The server can be run directly using Python:

```bash
venv/bin/python -m mcp_simple_timeserver.web.server
```
This will start the server on `http://0.0.0.0:8000`.

### 3. Test the Server

You can test the running server from your command line using `curl`.

**List Tools Request:**
```bash
curl -X POST http://127.0.0.1:8000/mcp \
-H "Content-Type: application/json" \
-H "Accept: application/json, text/event-stream" \
-d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

**Tool Call Request (`get_server_time`):**
```bash
curl -X POST http://127.0.0.1:8000/mcp \
-H "Content-Type: application/json" \
-H "Accept: application/json, text/event-stream" \
-d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_server_time","arguments":{}}}'
```

**Tool Call Request (`get_hijri_date`):**
```bash
curl -X POST http://127.0.0.1:8000/mcp \
-H "Content-Type: application/json" \
-H "Accept: application/json, text/event-stream" \
-d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_hijri_date","arguments":{}}}'
```

**Tool Call Request (`get_persian_date` with Farsi output):**
```bash
curl -X POST http://127.0.0.1:8000/mcp \
-H "Content-Type: application/json" \
-H "Accept: application/json, text/event-stream" \
-d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"get_persian_date","arguments":{"language":"fa"}}}'
```

## Docker Deployment

The project includes a `Dockerfile.web` for easy containerization.

### 1. Build the Docker Image

```bash
docker build -f Dockerfile.web -t mcp-simple-timeserver:web .
```

### 2. Run the Docker Container

To run the container for use with a local reverse proxy (like Apache or Nginx), you should map the container's port only to the host's loopback interface:

```bash
docker run -d -p 127.0.0.1:8000:8000 --name timeserver-web mcp-simple-timeserver:web
```
This command does two important things:
1.  It runs the container in detached mode (`-d`).
2.  It maps port 8000 inside the container to port 8000 on the **host machine's localhost interface only** (`-p 127.0.0.1:8000:8000`).

This ensures the server is not directly accessible from the network, which is the recommended setup when placing it behind a reverse proxy. The server will be accessible at `http://127.0.0.1:8000` on the host machine.

### Changing the Port

The server is configured to run on port 8000 inside the container. While you shouldn't change the internal port without rebuilding the image, you can easily change which port it's mapped to on your host machine.

**Local Development:**

To run the server on a different port locally, you would need to modify the `server.py` file to change the port in the `app.run()` call. The port is currently hardcoded to 8000.

**Docker Deployment:**

To map the container to a different host port, change the first value in the `-p` parameter. The format is `-p <host_port>:<container_port>`.

```bash
# Map container's port 8000 to host's port 9000
docker run -d -p 127.0.0.1:9000:8000 --name timeserver-web mcp-simple-timeserver:web
```

The server will now be accessible at `http://127.0.0.1:9000` on the host. 

Also you can set the restart  policy to "always" - this way the container will run after reboots.

```bash

docker run -d --restart always -p 127.0.0.1:8001:8000 --name timeserver-web mcp-simple-timeserver:web
```

## Apache Reverse Proxy Configuration

*Important: FastMCP 2.x URL Path*

FastMCP 2.x expects requests at `/mcp` (without trailing slash). Requests to `/mcp/` will receive a 307 redirect. Configure your proxy accordingly.

### Example Configuration

```apache
<VirtualHost *:443>
    ServerName mcp.andybrandt.net
    
    # SSL Configuration (if using HTTPS)
    # SSLEngine on
    # SSLCertificateFile /path/to/cert.pem
    # SSLCertificateKeyFile /path/to/key.pem
    
    # Main proxy configuration - note: NO trailing slash on /mcp
    <Location /timeserver>
        ProxyPass http://127.0.0.1:8001/mcp
        ProxyPassReverse http://127.0.0.1:8001/mcp
        
        # Important headers
        ProxyPreserveHost On
        RequestHeader set X-Forwarded-Proto "https"
    </Location>
</VirtualHost>
```

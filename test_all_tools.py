#!/usr/bin/env python3
"""
Test script for mcp-simple-timeserver
Tests all available tools via JSON-RPC over stdio
"""

import json
import subprocess
import sys


def call_server(requests: list[dict], expected_responses: int = 2) -> list[dict]:
    """
    Send JSON-RPC requests to the MCP server and return responses.
    Reads responses line by line and waits for expected number.
    """
    import os
    import select

    # Build the input as newline-delimited JSON
    input_data = "\n".join(json.dumps(req) for req in requests) + "\n"

    # Set environment to ensure unbuffered output
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    # Run the server
    process = subprocess.Popen(
        [sys.executable, "-u", "-m", "mcp_simple_timeserver"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        env=env
    )

    # Write all input
    process.stdin.write(input_data)
    process.stdin.flush()

    # Read responses until we have enough or timeout
    responses = []
    import time
    start_time = time.time()
    timeout = 10  # seconds

    while len(responses) < expected_responses and (time.time() - start_time) < timeout:
        # Check if there's data to read (with a short timeout)
        if select.select([process.stdout], [], [], 0.1)[0]:
            line = process.stdout.readline()
            if not line:
                break  # EOF
            line = line.strip()
            if line and line.startswith("{"):
                try:
                    responses.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    # Clean up
    process.stdin.close()
    process.terminate()
    process.wait(timeout=2)

    return responses


def handshake() -> list[dict]:
    """Return the standard MCP handshake requests."""
    return [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "test-client", "version": "1.0"},
                "capabilities": {}
            }
        },
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        }
    ]


def call_tool(tool_name: str, arguments: dict, request_id: int) -> str | None:
    """
    Call a tool and return its text result, or None if failed.
    """
    requests = handshake() + [
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
    ]

    responses = call_server(requests)

    # Find the response with our request ID
    for response in responses:
        if response.get("id") == request_id and "result" in response:
            content = response["result"].get("content", [])
            if content and "text" in content[0]:
                return content[0]["text"]

    return None


def list_tools() -> int | None:
    """List tools and return the count, or None if failed."""
    requests = handshake() + [
        {
            "jsonrpc": "2.0",
            "id": 100,
            "method": "tools/list"
        }
    ]

    responses = call_server(requests)

    for response in responses:
        if response.get("id") == 100 and "result" in response:
            tools = response["result"].get("tools", [])
            return len(tools)

    return None


def check_server_version() -> tuple[str | None, str | None]:
    """
    Check server version from initialize response.
    Returns tuple of (reported_version, expected_version) or (None, expected) if failed.
    """
    from importlib.metadata import version as get_version

    expected_version = get_version("mcp-simple-timeserver")

    # Just send initialize request (no notification needed for this check)
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "test-client", "version": "1.0"},
                "capabilities": {}
            }
        }
    ]

    responses = call_server(requests, expected_responses=1)

    for response in responses:
        if response.get("id") == 1 and "result" in response:
            server_info = response["result"].get("serverInfo", {})
            reported_version = server_info.get("version")
            return (reported_version, expected_version)

    return (None, expected_version)


def main():
    """Run all tests."""
    print("=" * 50)
    print("  MCP Simple Timeserver - Tool Tests")
    print("=" * 50)
    print()

    # Test server version
    print("Testing: server version")
    print("  Checking version reported in initialize response...")
    reported_ver, expected_ver = check_server_version()
    if reported_ver is not None:
        if reported_ver == expected_ver:
            print(f"  Result: Version {reported_ver} (matches pyproject.toml)")
        else:
            print(f"  ERROR: Version mismatch!")
            print(f"    Reported: {reported_ver}")
            print(f"    Expected: {expected_ver}")
    else:
        print("  ERROR: Could not get server version from initialize response")
    print()

    # Test tools/list
    print("Testing: tools/list")
    print("  Listing all available tools...")
    tool_count = list_tools()
    if tool_count is not None:
        print(f"  Result: Found {tool_count} tools")
        if tool_count != 6:
            print(f"  WARNING: Expected 6 tools, got {tool_count}")
    else:
        print("  ERROR: Could not list tools")
    print()

    # Define tests: (tool_name, arguments, description, request_id)
    tests = [
        # Basic tools
        ("get_local_time", {}, "Get local time and timezone", 10),
        ("get_utc", {}, "Get UTC time from NTP server", 20),

        # get_current_time with various calendar options
        ("get_current_time", {}, "Get current time (default, no calendars)", 30),
        ("get_current_time", {"calendar": "unix"}, "Get current time with Unix timestamp", 40),
        ("get_current_time", {"calendar": "isodate"}, "Get current time with ISO week date", 50),
        ("get_current_time", {"calendar": "hijri"}, "Get current time with Hijri calendar", 60),
        ("get_current_time", {"calendar": "japanese"}, "Get current time with Japanese calendar", 70),
        ("get_current_time", {"calendar": "hebrew"}, "Get current time with Hebrew calendar", 80),
        ("get_current_time", {"calendar": "persian"}, "Get current time with Persian calendar", 90),
        ("get_current_time", {"calendar": "unix,hijri,japanese"}, "Get current time with multiple calendars", 100),
        ("get_current_time", {"calendar": "unix,invalid,hebrew"}, "Get current time with invalid calendar (graceful)", 110),

        # get_current_time with location parameters
        ("get_current_time", {"city": "Warsaw"}, "Get time in Warsaw (city lookup)", 120),
        ("get_current_time", {"city": "Tokyo"}, "Get time in Tokyo (city lookup)", 130),
        ("get_current_time", {"country": "Poland"}, "Get time in Poland (country lookup)", 140),
        ("get_current_time", {"timezone": "America/New_York"}, "Get time with IANA timezone", 150),
        ("get_current_time", {"timezone": "+05:30"}, "Get time with UTC offset (+05:30)", 160),
        ("get_current_time", {"city": "Gotham"}, "Get time in invalid city (graceful fallback)", 170),
        ("get_current_time", {"city": "Tokyo", "calendar": "japanese"}, "Get Tokyo time with Japanese calendar", 180),
        ("get_current_time", {"timezone": "InvalidTZ"}, "Get time with invalid timezone (graceful fallback)", 190),

        # calculate_time_distance tests
        ("calculate_time_distance", {}, "Same params error (both default to now)", 200),
        ("calculate_time_distance", {"from_date": "2025-01-01", "to_date": "2025-01-01"}, "Same params error (explicit)", 205),
        ("calculate_time_distance", {"from_date": "2025-01-01", "to_date": "2025-01-15"}, "Basic date distance", 210),
        ("calculate_time_distance", {"from_date": "now", "to_date": "2025-12-31"}, "Countdown to date", 220),
        ("calculate_time_distance", {"from_date": "2025-01-01", "to_date": "2025-01-15", "unit": "weeks"}, "Distance in weeks", 230),
        ("calculate_time_distance", {"from_date": "2025-01-15", "to_date": "2025-01-01"}, "Past direction", 240),
        ("calculate_time_distance", {"from_date": "2025-01-01T09:00:00", "to_date": "2025-01-01T17:30:00"}, "Same day with time", 250),
        ("calculate_time_distance", {"from_date": "now", "to_date": "2025-06-01", "city": "Warsaw"}, "With location", 260),

        # get_holidays tests
        ("get_holidays", {"country": "Poland"}, "Get holidays for Poland (current year)", 300),
        ("get_holidays", {"country": "PL", "year": 2026}, "Get holidays with ISO code and year", 310),
        ("get_holidays", {"country": "Germany", "include_school_holidays": True}, "Get holidays with school holidays", 320),
        ("get_holidays", {"country": "United States"}, "Get holidays for USA (Nager.Date only)", 330),
        ("get_holidays", {"country": "InvalidCountry"}, "Get holidays for invalid country (graceful error)", 340),

        # is_holiday tests
        ("is_holiday", {"country": "Poland", "date": "2026-01-01"}, "Check New Year's Day in Poland", 350),
        ("is_holiday", {"country": "PL", "date": "2026-01-23"}, "Check non-holiday date in Poland", 360),
        ("is_holiday", {"country": "US"}, "Check today in USA (default date)", 370),
        ("is_holiday", {"country": "Germany", "date": "2026-12-25"}, "Check Christmas in Germany", 380),
        ("is_holiday", {"country": "XYZ", "date": "2026-01-01"}, "Check invalid country (graceful error)", 390),

        # is_holiday with city parameter tests
        ("is_holiday", {"city": "Warsaw", "date": "2026-01-19"}, "Check school holiday in Warsaw (winter break)", 400),
        ("is_holiday", {"city": "Krakow", "date": "2026-01-01"}, "Check New Year in Krakow (city lookup)", 410),
        ("is_holiday", {"city": "Berlin"}, "Check today in Berlin (city default date)", 420),
        ("is_holiday", {"city": "InvalidCity123"}, "Check invalid city (graceful error)", 430),

        # is_holiday with smaller/less obvious cities (international diversity)
        ("is_holiday", {"city": "Sieradz", "date": "2026-02-02"}, "Check school holiday in Sieradz, Poland (small city)", 440),
        ("is_holiday", {"city": "Segovia", "date": "2026-12-25"}, "Check Christmas in Segovia, Spain (small city)", 450),
        ("is_holiday", {"city": "Temuco", "date": "2026-09-18"}, "Check Independence Day in Temuco, Chile", 460),
        ("is_holiday", {"city": "Braga", "date": "2026-06-10"}, "Check Portugal Day in Braga, Portugal", 470),
        ("is_holiday", {"city": "Graz", "date": "2026-05-01"}, "Check Labour Day in Graz, Austria", 480),
    ]

    passed = 0
    failed = 0

    for tool_name, arguments, description, request_id in tests:
        print(f"Testing: {tool_name}")
        print(f"  {description}")

        result = call_tool(tool_name, arguments, request_id)

        if result is not None:
            print("  Result:")
            for line in result.split("\n"):
                print(f"    {line}")
            passed += 1
        else:
            print("  ERROR: No response received")
            failed += 1
        print()

    print("=" * 50)
    print(f"  Tests completed: {passed} passed, {failed} failed")
    print("=" * 50)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

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


def main():
    """Run all tests."""
    print("=" * 50)
    print("  MCP Simple Timeserver - Tool Tests")
    print("=" * 50)
    print()
    
    # Test tools/list
    print("Testing: tools/list")
    print("  Listing all available tools...")
    tool_count = list_tools()
    if tool_count is not None:
        print(f"  Result: Found {tool_count} tools")
    else:
        print("  ERROR: Could not list tools")
    print()
    
    # Define tests: (tool_name, arguments, description, request_id)
    tests = [
        ("get_local_time", {}, "Get local time and timezone", 10),
        ("get_utc", {}, "Get UTC time from NTP server", 20),
        ("get_iso_week_date", {}, "Get ISO 8601 week date", 30),
        ("get_unix_timestamp", {}, "Get Unix/POSIX timestamp", 40),
        ("get_hijri_date", {}, "Get Islamic (Hijri) calendar date", 50),
        ("get_japanese_era_date", {"language": "en"}, "Get Japanese Era date (English)", 60),
        ("get_japanese_era_date", {"language": "ja"}, "Get Japanese Era date (Kanji)", 70),
        ("get_hebrew_date", {"language": "en"}, "Get Hebrew calendar date (English)", 80),
        ("get_hebrew_date", {"language": "he"}, "Get Hebrew calendar date (Hebrew)", 90),
        ("get_persian_date", {"language": "en"}, "Get Persian calendar date (English)", 100),
        ("get_persian_date", {"language": "fa"}, "Get Persian calendar date (Farsi)", 110),
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

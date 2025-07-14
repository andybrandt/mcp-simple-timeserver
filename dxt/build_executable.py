#!/usr/bin/env python3
"""
PyInstaller build script for the MCP Simple Time Server.
This script compiles the server into a standalone executable.
"""

import subprocess
import sys
from pathlib import Path
import platform

def build():
    """Build the executable using PyInstaller."""
    root_dir = Path(__file__).parent.parent
    script_to_compile = root_dir / "mcp_simple_timeserver" / "server.py"
    icon_path = root_dir / "dxt" / "icon.png"
    
    # Platform-specific details
    system = platform.system()
    exe_name = "mcp-simple-timeserver"
    
    # Base command
    command = [
        "pyinstaller",
        "--name", exe_name,
        "--onefile",
        "--distpath", str(root_dir / "dxt" / "dist"),
        "--workpath", str(root_dir / "dxt" / "build"),
        "--specpath", str(root_dir / "dxt"),
    ]

    # Add Windows-specific option
    if system == "Windows":
        command.append("--noconsole")
    else:
        # Icons for executables are not supported in the same way on non-Windows
        # platforms and PNG is not a valid format for Windows executables.
        # The icon in the manifest is what's used by the client UI.
        command.append(f"--icon={icon_path}")

    # Add the script to compile
    command.append(str(script_to_compile))

    print(f"Running PyInstaller for {system}...")
    print(f"Command: {' '.join(command)}")
    
    try:
        subprocess.run(command, check=True)
        print("\nPyInstaller build successful.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\nPyInstaller build failed: {e}", file=sys.stderr)
        return False
    except FileNotFoundError:
        print("\nError: 'pyinstaller' command not found.", file=sys.stderr)
        print("Please ensure PyInstaller is installed (`pip install pyinstaller`).", file=sys.stderr)
        return False

if __name__ == "__main__":
    if not build():
        sys.exit(1) 
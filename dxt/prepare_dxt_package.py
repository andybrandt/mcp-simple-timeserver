#!/usr/bin/env python3
"""
Prepares the DXT package structure after the executable has been built.
"""

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
import tomllib

# Add the script's directory to the path to allow importing build_executable
sys.path.append(str(Path(__file__).parent.resolve()))
import build_executable

def to_display_name(name: str) -> str:
    """Converts a slug-like name to a display name.
    
    Example: "mcp-simple-timeserver" -> "MCP Simple Timeserver"
    """
    parts = name.split('-')
    transformed_parts = []
    for part in parts:
        if part.lower() == 'mcp':
            transformed_parts.append('MCP')
        else:
            transformed_parts.append(part.capitalize())
    return ' '.join(transformed_parts)

def prepare_dxt_package():
    """Prepare the DXT package directory structure."""
    # Determine paths
    script_dir = Path(__file__).parent
    root_dir = script_dir.parent
    build_dir = root_dir / "dxt_build"
    dist_dir = script_dir / "dist"
    
    # Run the PyInstaller build first
    print("--- Running PyInstaller build ---")
    if not build_executable.build():
        print("Build failed. Aborting.", file=sys.stderr)
        sys.exit(1)
    print("--- PyInstaller build complete ---")

    # Read metadata from pyproject.toml
    print("Reading metadata from pyproject.toml...")
    pyproject_path = root_dir / "pyproject.toml"
    try:
        with open(pyproject_path, "rb") as f:
            pyproject_data = tomllib.load(f)
        
        project_meta = pyproject_data["project"]
        project_name = project_meta["name"]
        project_version = project_meta["version"]
        project_description = project_meta["description"]
        author_info = project_meta["authors"][0]
        homepage_url = project_meta.get("urls", {}).get("Homepage", "")
        
        license_str = "MIT" # Default
        for classifier in project_meta.get("classifiers", []):
            if "License :: OSI Approved" in classifier:
                license_str = classifier.split("::")[-1].strip().replace(" License", "")

    except (FileNotFoundError, KeyError, IndexError) as e:
        print(f"Error: Could not read {pyproject_path} or it is malformed. {e}")
        sys.exit(1)
    
    # Generate display name
    display_name = to_display_name(project_name)

    # Clean previous DXT staging build
    if build_dir.exists():
        print(f"Cleaning previous DXT staging directory: {build_dir}")
        shutil.rmtree(build_dir)
    
    # Create directory structure
    print("Creating DXT staging directory...")
    build_dir.mkdir(parents=True, exist_ok=True)
    
    # Move the executable
    system = platform.system()
    exe_name = f"{project_name}.exe" if system == "Windows" else project_name
    src_exe_path = dist_dir / exe_name
    dest_exe_path = build_dir / exe_name
    print(f"Moving executable from {src_exe_path} to {dest_exe_path}...")
    shutil.move(str(src_exe_path), str(dest_exe_path))
    
    # Copy icon
    icon_path = script_dir / "icon.png"
    if icon_path.exists():
        print("Copying icon...")
        shutil.copy2(icon_path, build_dir / "icon.png")

    # Create simplified manifest
    manifest = {
        "dxt_version": "0.1",
        "name": project_name,
        "display_name": display_name,
        "version": project_version,
        "description": project_description,
        "author": {
            "name": author_info.get("name"),
            "email": author_info.get("email"),
            "url": "https://mcp.andybrandt.net/" # DXT-specific author URL
        },
        "license": license_str,
        "homepage": homepage_url,
        "repository": {
            "type": "git",
            "url": homepage_url
        },
        "keywords": ["time", "ntp", "mcp", "server", "utility"],
        "server": {
            "type": "binary",
            "mcp_config": {
                "command": f"${{__dirname}}/{exe_name}"
            }
        },
        "tools": [
            {
                "name": "get_server_time",
                "description": "Returns the current local time and timezone from the server hosting this tool."
            },
            {
                "name": "get_utc",
                "description": "Returns accurate UTC time from an NTP server."
            }
        ],
        "compatibility": {
            "claude_desktop": ">=0.10.0",
            "platforms": [platform.system().lower().replace("windows", "win32").replace("darwin", "darwin")]
        }
    }
    
    # Add OS-specific compatibility info if available from CI environment
    if system == 'Darwin' and os.getenv('RUNNER_OS_VERSION'):
        manifest['compatibility']['macos_version'] = f">={os.getenv('RUNNER_OS_VERSION')}"

    # Add icon if it exists
    if (build_dir / "icon.png").exists():
        manifest["icon"] = "icon.png"
    
    manifest_path = build_dir / "manifest.json"
    print(f"Creating manifest.json...")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    
    print(f"\nDXT package prepared in: {build_dir}")
    (build_dir / "version.txt").write_text(project_version)
    
    return build_dir

if __name__ == "__main__":
    prepare_dxt_package() 
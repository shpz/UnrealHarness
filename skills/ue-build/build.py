#!/usr/bin/env python3
"""
Generic Unreal Engine 5 project build script
=============================================
Auto-detect project file, resolve engine path, and build UE5 C++ project.
Supports both Launcher-installed and source-built engines.

Usage:
    python build.py
    python build.py --config Debug
    python build.py --project "D:\Projects\MyGame\MyGame.uproject"
    python build.py -h

Exit codes:
    0   Build succeeded
    1   Script error (project not found, engine not resolved, etc.)
    N   Build.bat exit code (propagated)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import winreg
from pathlib import Path

# ── ANSI color codes ──────────────────────────────────────────────────────────
_COLOR_CYAN    = "\033[36m"
_COLOR_GREEN   = "\033[32m"
_COLOR_YELLOW  = "\033[33m"
_COLOR_RED     = "\033[31m"
_COLOR_RESET   = "\033[0m"


def _color_print(msg: str, color: str = _COLOR_RESET) -> None:
    """Print with ANSI color if terminal supports it."""
    if sys.stdout.isatty():
        print(f"{color}{msg}{_COLOR_RESET}")
    else:
        print(msg)


def _error_exit(msg: str, code: int = 1) -> None:
    """Print error and exit with given code."""
    _color_print(msg, _COLOR_RED)
    sys.exit(code)


# ── 1. Project Discovery ────────────────────────────────────────────────────
def find_project_file(explicit_path: str) -> Path:
    """Resolve project file from explicit path or auto-detect in CWD."""
    if explicit_path:
        p = Path(explicit_path).resolve()
        if not p.exists():
            _error_exit(f"Project path does not exist: {explicit_path}")
        return p

    cwd = Path.cwd()
    uproject_files = list(cwd.glob("*.uproject"))

    if not uproject_files:
        _error_exit(
            "No .uproject file found in current directory. "
            "Please provide project path: --project \"path\\project.uproject\""
        )

    if len(uproject_files) == 1:
        return uproject_files[0].resolve()

    # Multiple projects found
    _color_print("Multiple UE5 projects found:", _COLOR_YELLOW)
    for i, f in enumerate(uproject_files):
        _color_print(f"  [{i}] {f.name}", _COLOR_CYAN)
    _color_print(
        "Please use --project parameter to specify which project to build",
        _COLOR_YELLOW,
    )
    sys.exit(1)


# ── 2. Engine Path Resolution ───────────────────────────────────────────────
def resolve_engine_path(project_file: Path) -> Path:
    """Read .uproject EngineAssociation and locate engine via Windows Registry."""
    try:
        with project_file.open("r", encoding="utf-8") as fh:
            uproject_data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        _error_exit(f"Failed to read/parse .uproject file: {exc}")

    engine_association = uproject_data.get("EngineAssociation")
    if not engine_association:
        _error_exit("Failed to read EngineAssociation field from .uproject")

    engine_path_str: str | None = None

    # Determine if it's a version number (e.g. "5.5") or GUID
    if re.match(r"^\d+\.\d+$", engine_association):
        # Launcher-installed engine
        reg_path = rf"SOFTWARE\EpicGames\Unreal Engine\{engine_association}"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                engine_path_str, _ = winreg.QueryValueEx(key, "InstalledDirectory")
        except FileNotFoundError:
            _error_exit(
                f"UE {engine_association} registry entry not found. "
                "Please verify installation via Epic Games Launcher."
            )
    else:
        # Source-built engine (GUID format)
        reg_path = rf"SOFTWARE\Epic Games\Unreal Engine\Builds\{engine_association}"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
                engine_path_str, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            _error_exit(
                "Source-built engine registry entry not found. "
                "Please verify engine is properly registered."
            )

    if not engine_path_str:
        _error_exit("Engine path is empty in registry.")

    engine_path = Path(engine_path_str)
    if not engine_path.exists():
        _error_exit(f"Engine path does not exist: {engine_path}")

    return engine_path


# ── 3. Target Derivation ────────────────────────────────────────────────────
def get_build_target(project_file: Path) -> str:
    """Derive editor build target from project file name."""
    project_name = project_file.stem
    return f"{project_name}Editor"


# ── 4. Build Execution ────────────────────────────────────────────────────────
def run_build(build_bat: Path, target: str, platform: str, configuration: str, project_file: Path) -> int:
    """Invoke Build.bat and return its exit code."""
    cmd = [
        str(build_bat),
        target,
        platform,
        configuration,
        str(project_file),
        "-waitmutex",
    ]

    _color_print("Executing command:", _COLOR_CYAN)
    _color_print(f"  {' '.join(cmd)}", _COLOR_CYAN)

    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except FileNotFoundError:
        _error_exit(f"Build.bat not found or not executable: {build_bat}")
    except OSError as exc:
        _error_exit(f"Failed to execute Build.bat: {exc}")
    # Unreachable, but satisfies type checker
    return 1  # pragma: no cover


# ── Main Flow ───────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generic Unreal Engine 5 project build script",
        epilog="Example: python build.py --config Debug",
    )
    parser.add_argument(
        "--project", "-p",
        metavar="PATH",
        default="",
        help="Path to .uproject file (optional, auto-detects from current directory)",
    )
    parser.add_argument(
        "--config", "-c",
        choices=["Development", "Debug", "Shipping", "Test"],
        default="Development",
        help="Build configuration (default: Development)",
    )
    parser.add_argument(
        "--platform", "-pl",
        choices=["Win64"],
        default="Win64",
        help="Target platform (default: Win64)",
    )
    args = parser.parse_args()

    # ── Discover project ──
    project_file = find_project_file(args.project)

    # ── Resolve engine ──
    engine_path = resolve_engine_path(project_file)

    # ── Derive target ──
    target = get_build_target(project_file)

    # ── Validate Build.bat ──
    build_bat = engine_path / "Engine" / "Build" / "BatchFiles" / "Build.bat"
    if not build_bat.exists():
        _error_exit(f"Build.bat not found: {build_bat}")

    # ── Print build summary ──
    _color_print("=" * 44, _COLOR_CYAN)
    _color_print("Unreal Engine 5 Project Build", _COLOR_CYAN)
    _color_print("=" * 44, _COLOR_CYAN)
    print(f"Project:      {project_file}")
    print(f"Target:       {target}")
    print(f"Platform:     {args.platform}")
    print(f"Configuration: {args.config}")
    print(f"Engine:       {engine_path}")
    _color_print("=" * 44, _COLOR_CYAN)

    # ── Execute build ──
    exit_code = run_build(build_bat, target, args.platform, args.config, project_file)

    if exit_code != 0:
        _color_print(f"Build failed with exit code: {exit_code}", _COLOR_RED)
        return exit_code

    _color_print("=" * 44, _COLOR_GREEN)
    _color_print("Build succeeded!", _COLOR_GREEN)
    _color_print("=" * 44, _COLOR_GREEN)
    return 0


if __name__ == "__main__":
    sys.exit(main())

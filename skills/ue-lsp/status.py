#!/usr/bin/env python3
"""Report UE C++ LSP prerequisites for clangd-based queries."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


CONFIGURATIONS = ("Development", "Debug", "Shipping", "Test")
PLATFORMS = ("Win64",)


@dataclass(frozen=True)
class StatusArgs:
    project: str
    source_file: str
    engine_root: str
    target: str
    platform: str
    configuration: str


def new_status_result(platform: str, configuration: str) -> dict[str, object]:
    return {
        "project_root": None,
        "uproject_path": None,
        "project_name": None,
        "engine_root": None,
        "target": None,
        "platform": platform,
        "configuration": configuration,
        "clangd_path": None,
        "compile_commands_path": None,
        "compile_commands_location": None,
        "compile_commands_mtime": None,
        "clangd_running": False,
        "index_state": "unknown",
        "health": "invalid",
        "caveats": [],
        "next_actions": [],
        "generate_compile_commands_command": None,
    }


def resolve_path(path: Path) -> str:
    return str(path.resolve())


def find_project_file(explicit_path: str) -> Path:
    if explicit_path:
        item = Path(explicit_path).resolve()
        if not item.exists():
            raise RuntimeError(f"--project path does not exist: {explicit_path}")

        if item.is_dir():
            files = list(item.glob("*.uproject"))
        else:
            if item.suffix != ".uproject":
                message = f"--project must be a .uproject file or directory containing one: {explicit_path}"
                raise RuntimeError(message)
            return item
    else:
        files = list(Path.cwd().glob("*.uproject"))

    if not files:
        raise RuntimeError("No .uproject file found")

    if len(files) > 1:
        names = ", ".join(resolve_path(file) for file in files)
        raise RuntimeError(f"Multiple .uproject files found; pass --project explicitly: {names}")

    return files[0].resolve()


def read_engine_association(project_file: Path) -> str | None:
    try:
        content = project_file.read_text(encoding="utf-8")
    except OSError:
        return None

    match = re.search(r'"EngineAssociation"\s*:\s*"([^"]+)"', content)
    if match:
        return match.group(1)
    return None


def query_registry(key_path: str, value_name: str) -> str | None:
    if sys.platform != "win32":
        return None

    try:
        result = subprocess.run(
            ["reg", "query", key_path, "/v", value_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped.startswith(value_name):
            continue
        parts = re.split(r"\s+", stripped, maxsplit=2)
        if len(parts) == 3:
            return parts[2]
    return None


def resolve_engine_path(project_file: Path, explicit_engine_root: str) -> Path | None:
    if explicit_engine_root:
        candidate = Path(explicit_engine_root).resolve()
        if candidate.exists():
            return candidate
        return None

    engine_association = read_engine_association(project_file)
    if not engine_association:
        return None

    if re.match(r"^\d+\.\d+", engine_association):
        candidate = query_registry(
            rf"HKLM\SOFTWARE\EpicGames\Unreal Engine\{engine_association}",
            "InstalledDirectory",
        )
    else:
        candidate = query_registry(
            rf"HKCU\SOFTWARE\Epic Games\Unreal Engine\Builds\{engine_association}",
            "Path",
        )

    if candidate:
        path = Path(candidate).resolve()
        if path.exists():
            return path

    return None


def find_clangd() -> str | None:
    return shutil.which("clangd")


def is_clangd_running() -> bool:
    if sys.platform != "win32":
        return False

    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq clangd.exe", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    return "clangd.exe" in result.stdout.lower()


def find_compile_commands(project_root: Path, engine_root: Path | None) -> tuple[Path | None, str | None]:
    """Return (path, location) where location is 'project_root' or 'engine_root'."""
    candidate = project_root / "compile_commands.json"
    if candidate.exists():
        return candidate.resolve(), "project_root"

    if engine_root is not None:
        engine_candidate = engine_root / "compile_commands.json"
        if engine_candidate.exists():
            return engine_candidate.resolve(), "engine_root"

    return None, None


def get_generated_header_caveats(file_path: str) -> list[str]:
    if not file_path:
        return []

    source_file = Path(file_path).resolve()
    if not source_file.exists():
        return [f"--source-file path does not exist: {file_path}"]

    try:
        content = source_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = source_file.read_text(encoding="utf-8", errors="replace")

    caveats: list[str] = []
    if ".generated.h" in content:
        for match in re.finditer(r'#include\s+"([^"]+\.generated\.h)"', content):
            generated_name = match.group(1)
            generated_path = source_file.parent / generated_name
            if not generated_path.exists():
                message = f"generated header is referenced but not found next to --source-file: {generated_name}"
                caveats.append(message)

    if re.search(r"GENERATED_BODY\s*\(", content):
        caveats.append("GENERATED_BODY is present; UHT/reflection semantics require UBT/UHT confirmation")

    return caveats


def quote_command_path(path: Path) -> str:
    return f'"{path}"'


def new_generate_compile_commands_command(
    engine_root: Path | None,
    project_file: Path,
    build_target: str,
    configuration: str,
    platform: str,
) -> str | None:
    if engine_root is None:
        return None

    ubt_exe = engine_root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.exe"
    if ubt_exe.exists():
        return f'{quote_command_path(ubt_exe)} -mode=GenerateClangDatabase -project={quote_command_path(project_file)} -game -engine {build_target} {configuration} {platform}'

    ubt_dll = engine_root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.dll"
    if ubt_dll.exists():
        return f'dotnet {quote_command_path(ubt_dll)} -mode=GenerateClangDatabase -project={quote_command_path(project_file)} -game -engine {build_target} {configuration} {platform}'

    build_bat = engine_root / "Engine" / "Build" / "BatchFiles" / "Build.bat"
    if build_bat.exists():
        return f'{quote_command_path(build_bat)} -mode=GenerateClangDatabase -project={quote_command_path(project_file)} -game -engine {build_target} {configuration} {platform}'

    return None


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def format_mtime(path: Path) -> str:
    timestamp = path.stat().st_mtime
    return datetime.fromtimestamp(timestamp, timezone.utc).astimezone().isoformat()


def parse_args() -> StatusArgs:
    values = {
        "project": "",
        "source_file": "",
        "engine_root": "",
        "target": "",
        "platform": "Win64",
        "configuration": "Development",
    }
    aliases = {
        "--project": "project",
        "--source-file": "source_file",
        "--engine-root": "engine_root",
        "--target": "target",
        "--platform": "platform",
        "--configuration": "configuration",
    }

    args = sys.argv[1:]
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in ("-h", "--help"):
            print("Usage: python status.py [--project <Project.uproject>] [--source-file <File.cpp>] [--engine-root <EngineRoot>] [--target <Target>] [--platform Win64] [--configuration Development|Debug|Shipping|Test]")
            sys.exit(0)
        if "=" in arg:
            name, value = arg.split("=", 1)
        else:
            name = arg
            index += 1
            if index >= len(args):
                raise RuntimeError(f"Missing value for argument: {name}")
            value = args[index]

        key = aliases.get(name)
        if key is None:
            raise RuntimeError(f"Unknown argument: {name}")
        values[key] = value
        index += 1

    if values["platform"] not in PLATFORMS:
        raise RuntimeError(f"Unsupported platform: {values['platform']}")
    if values["configuration"] not in CONFIGURATIONS:
        raise RuntimeError(f"Unsupported configuration: {values['configuration']}")

    return StatusArgs(
        project=values["project"],
        source_file=values["source_file"],
        engine_root=values["engine_root"],
        target=values["target"],
        platform=values["platform"],
        configuration=values["configuration"],
    )


def main() -> int:
    args = parse_args()
    result = new_status_result(args.platform, args.configuration)

    try:
        project_file = find_project_file(args.project)
        project_root = project_file.parent
        project_name = project_file.stem
        target = args.target or f"{project_name}Editor"

        engine_root = resolve_engine_path(project_file, args.engine_root)
        clangd_path = find_clangd()
        compile_commands_path, compile_commands_location = find_compile_commands(project_root, engine_root)
        caveats: list[str] = []
        next_actions: list[str] = []

        if engine_root is None:
            caveats.append("EngineAssociation could not be resolved from registry")
            next_actions.append("provide_engine_root_or_register_engine")

        if clangd_path is None:
            caveats.append("clangd was not found on PATH")
            next_actions.append("install_or_add_clangd_to_path")

        if compile_commands_path is None:
            caveats.append("compile_commands.json is missing from project root")
            next_actions.append("generate_compile_database")
        elif compile_commands_location == "engine_root":
            caveats.append(
                "compile_commands.json was found in engine root, not project root; "
                + "clangd will not pick it up for project files without a .clangd pointing at it"
            )
            next_actions.append("create_clangd_config_pointing_to_engine_root")

        for caveat in get_generated_header_caveats(args.source_file):
            caveats.append(caveat)
            next_actions.append("refresh_generated_headers")

        health = "ok"
        if compile_commands_path is None:
            health = "broken"
        elif compile_commands_location == "engine_root" or engine_root is None or clangd_path is None:
            health = "degraded"

        result.update(
            {
                "project_root": resolve_path(project_root),
                "uproject_path": resolve_path(project_file),
                "project_name": project_name,
                "engine_root": resolve_path(engine_root) if engine_root else None,
                "target": target,
                "clangd_path": clangd_path,
                "compile_commands_path": resolve_path(compile_commands_path) if compile_commands_path else None,
                "compile_commands_location": compile_commands_location,
                "compile_commands_mtime": format_mtime(compile_commands_path) if compile_commands_path else None,
                "clangd_running": is_clangd_running(),
                "health": health,
                "caveats": caveats,
                "next_actions": unique(next_actions),
                "generate_compile_commands_command": new_generate_compile_commands_command(
                    engine_root,
                    project_file,
                    target,
                    args.configuration,
                    args.platform,
                ),
            }
        )
    except Exception as exc:
        result["health"] = "invalid"
        result["caveats"] = [str(exc)]
        result["next_actions"] = ["provide_project_path"]

    print(json.dumps(result, indent=4))
    return 0


if __name__ == "__main__":
    sys.exit(main())

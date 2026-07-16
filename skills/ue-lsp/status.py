#!/usr/bin/env python3
"""Report UE C++ LSP prerequisites for workspace-local clangd queries."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONFIGURATIONS = ("Development", "Debug", "Shipping", "Test")
PLATFORMS = ("Win64",)


@dataclass(frozen=True)
class StatusArgs:
    project: str = ""
    source_file: str = ""
    engine_root: str = ""
    target: str = ""
    platform: str = "Win64"
    configuration: str = "Development"


def resolve_path(path: Path) -> str:
    return str(path.resolve())


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def find_project_file(explicit_path: str) -> Path:
    if explicit_path:
        item = Path(explicit_path).resolve()
        if not item.exists():
            raise RuntimeError(f"--project path does not exist: {explicit_path}")
        if item.is_dir():
            files = list(item.glob("*.uproject"))
        elif item.suffix.lower() == ".uproject":
            return item
        else:
            raise RuntimeError(f"--project must be a .uproject file or directory containing one: {explicit_path}")
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
        content = project_file.read_text(encoding="utf-8-sig")
    except OSError:
        return None
    match = re.search(r'"EngineAssociation"\s*:\s*"([^"]+)"', content)
    return match.group(1) if match else None


def query_registry(key_path: str, value_name: str) -> str | None:
    if sys.platform != "win32":
        return None
    try:
        result = subprocess.run(
            ["reg", "query", key_path, "/v", value_name],
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith(value_name):
            parts = re.split(r"\s+", stripped, maxsplit=2)
            if len(parts) == 3:
                return parts[2]
    return None


def resolve_engine_path(project_file: Path, explicit_engine_root: str) -> Path | None:
    if explicit_engine_root:
        candidate = Path(explicit_engine_root).resolve()
        return candidate if candidate.exists() else None
    association = read_engine_association(project_file)
    if not association:
        return None
    if re.match(r"^\d+\.\d+", association):
        candidate = query_registry(rf"HKLM\SOFTWARE\EpicGames\Unreal Engine\{association}", "InstalledDirectory")
    else:
        candidate = query_registry(rf"HKCU\SOFTWARE\Epic Games\Unreal Engine\Builds\{association}", "Path")
    if candidate:
        path = Path(candidate).resolve()
        if path.exists():
            return path
    return None


def find_clangd() -> str | None:
    return shutil.which("clangd")


def clangd_version(clangd_path: str | None) -> str | None:
    if not clangd_path:
        return None
    try:
        result = subprocess.run(
            [clangd_path, "--version"], check=False, capture_output=True, text=True, errors="replace", timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    first_line = (result.stdout or result.stderr).splitlines()
    return first_line[0].strip() if first_line else None


def is_clangd_running() -> bool:
    if sys.platform != "win32":
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq clangd.exe", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "clangd.exe" in result.stdout.lower()


def _entry_file(entry: dict[str, Any]) -> Path | None:
    raw_file = entry.get("file")
    if not isinstance(raw_file, str) or not raw_file.strip():
        return None
    candidate = Path(raw_file)
    if not candidate.is_absolute():
        directory = entry.get("directory")
        if isinstance(directory, str) and directory.strip():
            candidate = Path(directory) / candidate
    try:
        return candidate.resolve()
    except OSError:
        return candidate.absolute()


def _looks_like_other_benchmark_workspace(path: Path, project_root: Path) -> bool:
    if _is_relative_to(path, project_root):
        return False
    normalized = str(path).replace("/", "\\").lower()
    project_name = project_root.name.lower()
    marker = f"\\workspace\\{project_name}\\source\\"
    return marker in normalized or ("\\br\\" in normalized and f"\\{project_name}\\source\\" in normalized)


def project_translation_units(project_root: Path) -> set[Path]:
    source_root = project_root / "Source"
    if not source_root.exists():
        return set()
    return {path.resolve() for path in source_root.rglob("*.cpp") if path.is_file()}


def validate_compile_commands(
    path: Path,
    project_root: Path,
    source_file: Path | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "state": "missing",
        "entry_count": 0,
        "project_translation_unit_count": 0,
        "covered_project_translation_unit_count": 0,
        "missing_translation_units": [],
        "deleted_translation_units": [],
        "requested_source_covered": None,
        "foreign_workspace_paths": [],
        "missing_response_files": [],
        "message": "compile_commands.json is missing from project root",
    }
    if not path.exists():
        return result
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        result.update(state="malformed", message=f"compile_commands.json is not valid JSON: {exc}")
        return result
    if not isinstance(data, list):
        result.update(state="malformed", message="compile_commands.json root must be an array")
        return result
    if not data:
        result.update(state="empty", message="compile_commands.json is an empty array")
        return result

    entry_files: set[Path] = set()
    invalid_entries = 0
    foreign: list[str] = []
    missing_response_files: list[str] = []
    for entry in data:
        if not isinstance(entry, dict):
            invalid_entries += 1
            continue
        has_command = isinstance(entry.get("command"), str) and bool(entry["command"].strip())
        has_arguments = isinstance(entry.get("arguments"), list) and bool(entry["arguments"])
        entry_file = _entry_file(entry)
        if entry_file is None or not (has_command or has_arguments):
            invalid_entries += 1
            continue
        entry_files.add(entry_file)
        if _looks_like_other_benchmark_workspace(entry_file, project_root):
            foreign.append(str(entry_file))
        command = entry.get("command")
        if isinstance(command, str):
            for quoted, bare in re.findall(r'@(?:"([^"]+\.rsp)"|([^\s"]+\.rsp))', command, flags=re.IGNORECASE):
                response_file = Path(quoted or bare)
                if not response_file.is_absolute() and isinstance(entry.get("directory"), str):
                    response_file = Path(entry["directory"]) / response_file
                if not response_file.exists():
                    missing_response_files.append(str(response_file.resolve()))

    result["entry_count"] = len(data)
    if invalid_entries:
        result.update(
            state="malformed",
            message=f"compile_commands.json has {invalid_entries} entries without file and command/arguments",
        )
        return result
    if foreign:
        result.update(
            state="wrong-workspace",
            foreign_workspace_paths=foreign[:20],
            message="compile_commands.json contains translation units from another benchmark workspace",
        )
        return result
    if missing_response_files:
        result.update(
            state="stale",
            missing_response_files=sorted(set(missing_response_files))[:50],
            message="compile_commands.json references missing compiler response files and must be regenerated",
        )
        return result

    source_root = (project_root / "Source").resolve()
    actual_tus = project_translation_units(project_root)
    covered_tus = {item for item in entry_files if item.suffix.lower() == ".cpp" and _is_relative_to(item, source_root)}
    missing_tus = sorted(actual_tus - covered_tus, key=lambda item: str(item).lower())
    deleted_tus = sorted(
        (item for item in covered_tus - actual_tus if _is_relative_to(item, source_root)),
        key=lambda item: str(item).lower(),
    )
    result.update(
        project_translation_unit_count=len(actual_tus),
        covered_project_translation_unit_count=len(covered_tus),
        missing_translation_units=[str(item) for item in missing_tus],
        deleted_translation_units=[str(item) for item in deleted_tus],
    )
    if not covered_tus:
        result.update(state="wrong-workspace", message="compile_commands.json has no translation unit under this project's Source directory")
        return result

    requested = source_file.resolve() if source_file and source_file.suffix.lower() == ".cpp" else None
    if requested is not None:
        covered = any(_same_path(requested, item) for item in entry_files)
        result["requested_source_covered"] = covered
        if not covered:
            result.update(state="source-not-covered", message="requested .cpp source file is not covered by compile_commands.json")
            return result

    compdb_mtime = path.stat().st_mtime
    metadata_files = list(project_root.glob("*.uproject"))
    metadata_files.extend((project_root / "Source").rglob("*.Build.cs"))
    metadata_files.extend((project_root / "Source").rglob("*.Target.cs"))
    newer_metadata = [str(item.resolve()) for item in metadata_files if item.exists() and item.stat().st_mtime > compdb_mtime]
    if newer_metadata or missing_tus or deleted_tus:
        result.update(
            state="stale",
            newer_project_metadata=newer_metadata,
            message="compile_commands.json needs refresh because project metadata or the translation-unit set changed",
        )
        return result

    result.update(state="valid", message="workspace-local compile_commands.json is valid")
    return result


def get_generated_header_caveats(file_path: str, project_root: Path) -> list[str]:
    if not file_path:
        return []
    source_file = Path(file_path)
    if not source_file.is_absolute():
        source_file = project_root / source_file
    source_file = source_file.resolve()
    if not source_file.exists():
        return [f"--source-file path does not exist: {file_path}"]
    try:
        content = source_file.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        content = source_file.read_text(encoding="utf-8-sig", errors="replace")
    if ".generated.h" in content or re.search(r"GENERATED_BODY\s*\(", content):
        return [
            "source uses UnrealHeaderTool-generated reflection code; validate reflection/generated-header issues with UBT/UHT"
        ]
    return []


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
    output = f'-OutputDir={quote_command_path(project_file.parent)}'
    common = (
        f'-mode=GenerateClangDatabase -project={quote_command_path(project_file)} -game -engine '
        f'{output} {build_target} {configuration} {platform}'
    )
    ubt_exe = engine_root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.exe"
    if ubt_exe.exists():
        return f"{quote_command_path(ubt_exe)} {common}"
    ubt_dll = engine_root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.dll"
    if ubt_dll.exists():
        return f"dotnet {quote_command_path(ubt_dll)} {common}"
    build_bat = engine_root / "Engine" / "Build" / "BatchFiles" / "Build.bat"
    if build_bat.exists():
        return f"{quote_command_path(build_bat)} {common}"
    return None


def unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def format_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).astimezone().isoformat()


def collect_status(args: StatusArgs) -> dict[str, Any]:
    result: dict[str, Any] = {
        "project_root": None,
        "uproject_path": None,
        "project_name": None,
        "engine_root": None,
        "target": None,
        "platform": args.platform,
        "configuration": args.configuration,
        "clangd_path": None,
        "clangd_version": None,
        "expected_compile_commands_path": None,
        "compile_commands_path": None,
        "compile_commands_location": "project_root",
        "compile_commands_mtime": None,
        "compile_commands_health": "missing",
        "compile_commands_validation": None,
        "legacy_engine_compile_commands_path": None,
        "legacy_engine_compile_commands_mtime": None,
        "clangd_running": False,
        "index_state": "unknown",
        "health": "invalid",
        "caveats": [],
        "next_actions": [],
        "generate_compile_commands_command": None,
    }
    try:
        project_file = find_project_file(args.project)
        project_root = project_file.parent
        source_file = None
        if args.source_file:
            source_file = Path(args.source_file)
            if not source_file.is_absolute():
                source_file = project_root / source_file
        engine_root = resolve_engine_path(project_file, args.engine_root)
        clangd_path = find_clangd()
        expected_compdb = (project_root / "compile_commands.json").resolve()
        legacy_compdb = (engine_root / "compile_commands.json").resolve() if engine_root else None
        validation = validate_compile_commands(expected_compdb, project_root, source_file)
        caveats: list[str] = []
        next_actions: list[str] = []

        if engine_root is None:
            caveats.append("EngineAssociation could not be resolved from the registry or --engine-root")
            next_actions.append("provide_engine_root_or_register_engine")
        if clangd_path is None:
            caveats.append("clangd was not found on PATH")
            next_actions.append("install_or_add_clangd_to_path")
        state = validation["state"]
        if state != "valid":
            caveats.append(str(validation["message"]))
            next_actions.append("generate_workspace_compile_database")
        if legacy_compdb and legacy_compdb.exists():
            caveats.append(
                "an Engine-root compile_commands.json exists as legacy/external state; it is not used, modified, or recommended"
            )
        caveats.extend(get_generated_header_caveats(args.source_file, project_root))

        if state in {"missing", "malformed", "empty", "wrong-workspace", "source-not-covered", "stale"}:
            health = "broken"
        elif engine_root is None or clangd_path is None:
            health = "degraded"
        else:
            health = "ok"

        result.update(
            project_root=resolve_path(project_root),
            uproject_path=resolve_path(project_file),
            project_name=project_file.stem,
            engine_root=resolve_path(engine_root) if engine_root else None,
            target=args.target or f"{project_file.stem}Editor",
            clangd_path=clangd_path,
            clangd_version=clangd_version(clangd_path),
            expected_compile_commands_path=resolve_path(expected_compdb),
            compile_commands_path=resolve_path(expected_compdb) if expected_compdb.exists() else None,
            compile_commands_mtime=format_mtime(expected_compdb) if expected_compdb.exists() else None,
            compile_commands_health=state,
            compile_commands_validation=validation,
            legacy_engine_compile_commands_path=resolve_path(legacy_compdb) if legacy_compdb and legacy_compdb.exists() else None,
            legacy_engine_compile_commands_mtime=format_mtime(legacy_compdb) if legacy_compdb and legacy_compdb.exists() else None,
            clangd_running=is_clangd_running(),
            health=health,
            caveats=unique(caveats),
            next_actions=unique(next_actions),
            generate_compile_commands_command=new_generate_compile_commands_command(
                engine_root,
                project_file,
                args.target or f"{project_file.stem}Editor",
                args.configuration,
                args.platform,
            ),
        )
    except Exception as exc:
        result["health"] = "invalid"
        result["caveats"] = [str(exc)]
        result["next_actions"] = ["provide_project_path"]
    return result


def parse_args(argv: list[str] | None = None) -> StatusArgs:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="")
    parser.add_argument("--source-file", default="")
    parser.add_argument("--engine-root", default="")
    parser.add_argument("--target", default="")
    parser.add_argument("--platform", choices=PLATFORMS, default="Win64")
    parser.add_argument("--configuration", choices=CONFIGURATIONS, default="Development")
    ns = parser.parse_args(argv)
    return StatusArgs(**vars(ns))


def main(argv: list[str] | None = None) -> int:
    print(json.dumps(collect_status(parse_args(argv)), indent=4, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

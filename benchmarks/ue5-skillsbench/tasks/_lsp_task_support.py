"""Shared helpers for semantic LSP benchmark tasks."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def read_engine_association(uproject: Path) -> str | None:
    match = re.search(r'"EngineAssociation"\s*:\s*"([^"]+)"', uproject.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def _query_registry(key_path: str, value_name: str) -> str | None:
    if sys.platform != "win32":
        return None
    result = subprocess.run(
        ["reg", "query", key_path, "/v", value_name],
        check=False,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=15,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith(value_name):
            parts = re.split(r"\s+", stripped, maxsplit=2)
            if len(parts) == 3:
                return parts[2]
    return None


def resolve_engine_root(uproject: Path) -> Path:
    association = read_engine_association(uproject)
    if not association:
        raise RuntimeError(f"EngineAssociation missing from {uproject}")

    if re.match(r"^\d+\.\d+", association):
        raw = _query_registry(
            rf"HKLM\SOFTWARE\EpicGames\Unreal Engine\{association}",
            "InstalledDirectory",
        )
    else:
        raw = _query_registry(
            rf"HKCU\SOFTWARE\Epic Games\Unreal Engine\Builds\{association}",
            "Path",
        )

    if not raw:
        raise RuntimeError(f"Could not resolve Unreal Engine association {association!r} from registry")
    root = Path(raw).resolve()
    if not root.exists():
        raise RuntimeError(f"Resolved engine root does not exist: {root}")
    return root


def replace_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)


def generate_compile_database(project_path: Path) -> Path:
    project_path = project_path.resolve()
    uproject = project_path / "TPSample.uproject"
    if not uproject.exists():
        raise RuntimeError(f"uproject missing: {uproject}")

    engine_root = resolve_engine_root(uproject)
    ubt_exe = engine_root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.exe"
    ubt_dll = engine_root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.dll"

    common = [
        "-mode=GenerateClangDatabase",
        f"-project={uproject}",
        "-game",
        "-engine",
        f"-OutputDir={project_path}",
        "TPSampleEditor",
        "Development",
        "Win64",
    ]
    if ubt_exe.exists():
        command = [str(ubt_exe), *common]
    elif ubt_dll.exists():
        command = ["dotnet", str(ubt_dll), *common]
    else:
        raise RuntimeError(f"UnrealBuildTool not found under {engine_root}")

    compdb = project_path / "compile_commands.json"
    if compdb.exists():
        compdb.unlink()

    print("Generating workspace-local compile_commands.json")
    print(subprocess.list2cmdline(command))
    result = subprocess.run(
        command,
        cwd=str(project_path),
        check=False,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=900,
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"GenerateClangDatabase failed with exit code {result.returncode}")

    validate_compile_database(compdb, project_path)
    return compdb


def validate_compile_database(path: Path, project_path: Path) -> list[dict[str, object]]:
    if not path.exists():
        raise RuntimeError(f"compile_commands.json does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"compile_commands.json is invalid: {exc}") from exc
    if not isinstance(data, list) or not data:
        raise RuntimeError("compile_commands.json must be a non-empty JSON array")

    project_source = str((project_path / "Source" / "TPSample").resolve()).lower().replace("/", "\\")
    contains_project_tu = False
    for entry in data:
        if not isinstance(entry, dict):
            continue
        raw_file = str(entry.get("file", "")).lower().replace("/", "\\")
        if raw_file.startswith(project_source) and raw_file.endswith(".cpp"):
            contains_project_tu = True
            break
    if not contains_project_tu:
        raise RuntimeError("compile_commands.json has no TPSample C++ translation unit")
    return data


def resolve_and_validate_reported_compdb(project_path: Path, raw_path: object) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise RuntimeError("compile_commands_path must be a non-empty string")
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = project_path / candidate
    candidate = candidate.resolve()
    validate_compile_database(candidate, project_path.resolve())
    return candidate


def git_changes(project_path: Path, *pathspecs: str) -> list[str]:
    command = ["git", "-c", "core.excludesfile=", "status", "--porcelain", "--"]
    command.extend(pathspecs)
    result = subprocess.run(
        command,
        cwd=str(project_path),
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def normalized_relative_path(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().replace("\\", "/").lstrip("./")

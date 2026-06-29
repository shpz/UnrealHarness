"""Preflight checks for the benchmark environment."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .config import BenchmarkConfig
from .unreal import get_engine_paths, read_uproject


def check_windows_platform() -> tuple[bool, str]:
    import platform
    ok = platform.system() == "Windows"
    return ok, f"system={platform.system()} platform={platform.platform()}"



def check_git() -> tuple[bool, str]:
    cmd = shutil.which("git")
    if cmd is None:
        return False, "git not found in PATH"
    return True, cmd


def check_project_source(repo_root: Path, source: str) -> tuple[bool, str]:
    path = repo_root / source
    return path.exists(), str(path)


def check_uproject(repo_root: Path, source: str, uproject: str) -> tuple[bool, str]:
    path = repo_root / source / uproject
    return path.exists(), str(path)


def check_engine_association(repo_root: Path, source: str, uproject: str, expected: str) -> tuple[bool, str]:
    path = repo_root / source / uproject
    if not path.exists():
        return False, f"uproject not found: {path}"
    try:
        descriptor = read_uproject(path)
        actual = descriptor.get("EngineAssociation", "")
        return actual == expected, f"uproject={actual} config={expected}"
    except Exception as e:
        return False, str(e)


def check_engine_paths(repo_root: Path, source: str, uproject: str) -> tuple[bool, str]:
    path = repo_root / source / uproject
    if not path.exists():
        return False, f"uproject not found: {path}"
    try:
        paths = get_engine_paths(path)
        paths.validate()
        return True, str(paths.engine_root)
    except Exception as e:
        return False, str(e)


def run_preflight(config: BenchmarkConfig, repo_root: Path) -> dict:
    checks = []
    ok, detail = check_windows_platform()
    checks.append({"name": "windows-platform", "passed": ok, "detail": detail})

    ok, detail = check_git()
    checks.append({"name": "git-command", "passed": ok, "detail": detail})

    ok, detail = check_project_source(repo_root, config.project.source)
    checks.append({"name": "baseline-project", "passed": ok, "detail": detail})

    ok, detail = check_uproject(repo_root, config.project.source, config.project.uproject)
    checks.append({"name": "baseline-uproject", "passed": ok, "detail": detail})

    ok, detail = check_engine_association(
        repo_root, config.project.source, config.project.uproject, config.project.engine_association
    )
    checks.append({"name": "engine-association", "passed": ok, "detail": detail})

    ok, detail = check_engine_paths(repo_root, config.project.source, config.project.uproject)
    checks.append({"name": "engine-paths", "passed": ok, "detail": detail})

    failed = [c for c in checks if not c["passed"]]
    if failed:
        details = "\n".join(f"- {c['name']}: {c['detail']}" for c in failed)
        raise RuntimeError(f"Preflight failed:\n{details}")

    return {"passed": True, "checks": checks}

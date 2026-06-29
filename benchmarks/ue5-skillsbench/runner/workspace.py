"""Workspace preparation: project copy, git init, skill injection, safety guards."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .config import BenchmarkConfig, ConditionConfig


class SafetyError(Exception):
    pass


def _is_inside(child: Path, parent: Path) -> bool:
    child = child.resolve()
    parent = parent.resolve()
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _paths_equal(a: Path, b: Path) -> bool:
    return a.resolve() == b.resolve()


def assert_safe_path(path: Path, run_root: Path, repo_root: Path, baseline_project: Path, engine_root: Optional[Path] = None) -> Path:
    if not path.parts:
        raise SafetyError("Refusing unsafe path: empty")

    if _paths_equal(path, repo_root):
        raise SafetyError("Refusing unsafe path: repository root")

    if _paths_equal(path, baseline_project) or _is_inside(path, baseline_project):
        raise SafetyError("Refusing unsafe path: baseline project")

    if engine_root and (_paths_equal(path, engine_root) or _is_inside(path, engine_root)):
        raise SafetyError("Refusing unsafe path: engine installation")

    if not _is_inside(path, run_root):
        raise SafetyError("Refusing unsafe path: outside run root")

    return path


def copy_project_filtered(
    source: Path,
    destination: Path,
    exclude_dirs: list[str],
) -> None:
    if destination.exists():
        raise SafetyError(f"Destination already exists: {destination}")
    destination.mkdir(parents=True)

    for item in source.iterdir():
        if item.name in exclude_dirs:
            continue
        dest = destination / item.name
        if item.is_dir():
            copy_project_filtered(item, dest, exclude_dirs)
        else:
            shutil.copy2(item, dest)


def init_git(project_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=str(project_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "SkillsBench Runner"], cwd=str(project_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "skillsbench@example.invalid"], cwd=str(project_path), check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=str(project_path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Baseline workspace"], cwd=str(project_path), check=True, capture_output=True)

    result = subprocess.run(["git", "status", "--short"], cwd=str(project_path), capture_output=True, text=True, check=True)
    if result.stdout.strip():
        raise RuntimeError(f"Workspace git status is not clean: {result.stdout}")


def inject_skills(
    repo_root: Path,
    workspace_root: Path,
    config: BenchmarkConfig,
    condition: ConditionConfig,
) -> Optional[Path]:
    if not condition.skills:
        return None

    # Inject into workspace/skills/ for generic access
    skills_root = workspace_root / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)

    # Build a lookup map from skill name to its configured path
    skill_paths = {s.name: s.path for s in config.skills}

    for skill_name in condition.skills:
        if skill_name not in skill_paths:
            raise RuntimeError(f"Condition references undeclared skill '{skill_name}'")
        source = repo_root / skill_paths[skill_name]
        if not source.exists():
            raise RuntimeError(f"Skill directory does not exist: {source}")
        dest = skills_root / skill_name
        if dest.exists():
            raise RuntimeError(f"Skill destination already exists: {dest}")
        shutil.copytree(source, dest)

    return skills_root


def prepare_workspace(
    repo_root: Path,
    run_root: Path,
    run_id: str,
    task_id: str,
    condition: ConditionConfig,
    trial: int,
    config: BenchmarkConfig,
) -> dict:
    """Create workspace, copy project, init git, inject skills."""
    run_dir = run_root / run_id
    workspace_root = run_dir / "workspace"
    artifacts_root = run_dir / "artifacts"
    automation_root = artifacts_root / "automation"

    for d in [workspace_root, artifacts_root, automation_root]:
        d.mkdir(parents=True, exist_ok=True)

    project_source = repo_root / config.project.source
    project_destination = workspace_root / "TPSample"
    baseline_project = repo_root / config.project.source

    # Safety checks
    assert_safe_path(run_dir, run_root, repo_root, baseline_project)
    assert_safe_path(project_destination, run_root, repo_root, baseline_project)
    assert_safe_path(artifacts_root, run_root, repo_root, baseline_project)

    copy_project_filtered(project_source, project_destination, config.runner.copy_excludes)
    init_git(project_destination)
    skills_root = inject_skills(repo_root, workspace_root, config, condition)

    return {
        "run_dir": str(run_dir),
        "workspace_root": str(workspace_root),
        "artifacts_root": str(artifacts_root),
        "automation_root": str(automation_root),
        "project_destination": str(project_destination),
        "skills_root": str(skills_root) if skills_root else None,
        "result_json": str(run_dir / "result.json"),
    }

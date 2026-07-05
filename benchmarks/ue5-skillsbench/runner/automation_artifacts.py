"""Collect Automation artifacts from a trial workspace."""
from __future__ import annotations

import shutil
from pathlib import Path


def collect_automation_artifacts(project_path: Path, artifacts_path: Path) -> list[Path]:
    automation_artifacts = artifacts_path / "automation"
    automation_artifacts.mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []

    index = _latest_file(project_path / "Saved" / "Automation" / "Reports", "index.json")
    if index:
        copied.append(_copy_file(index, automation_artifacts / "index.json"))

    results = project_path / "Saved" / "Automation" / "autotest_results.json"
    if results.exists():
        copied.append(_copy_file(results, automation_artifacts / "autotest_results.json"))

    markdown = _latest_markdown_report(project_path / "Saved" / "Automation" / "Reports")
    if markdown:
        copied.append(_copy_file(markdown, automation_artifacts / "report.md"))

    editor_log = _latest_editor_log(project_path)
    if editor_log:
        copied.append(_copy_file(editor_log, automation_artifacts / "editor.log"))

    return copied


def _copy_file(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def _latest_file(root: Path, name: str) -> Path | None:
    if not root.exists():
        return None
    candidates = [path for path in root.rglob(name) if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _latest_markdown_report(root: Path) -> Path | None:
    if not root.exists():
        return None
    candidates = [path for path in root.rglob("*.md") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _latest_editor_log(project_path: Path) -> Path | None:
    logs_root = project_path / "Saved" / "Logs"
    candidates: dict[Path, None] = {}
    if logs_root.exists():
        for pattern in ["UnrealEditor-Cmd.log", "UnrealEditor*.log", f"{project_path.name}*.log"]:
            for path in logs_root.glob(pattern):
                if path.is_file():
                    candidates[path] = None
    reports_root = project_path / "Saved" / "Automation" / "Reports"
    if reports_root.exists():
        for path in reports_root.rglob("automation.log"):
            if path.is_file():
                candidates[path] = None
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)

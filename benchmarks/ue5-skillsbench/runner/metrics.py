"""Git diff metrics collection."""
from __future__ import annotations

import subprocess
from pathlib import Path


def git_add_untracked(project_path: Path) -> None:
    subprocess.run(
        ["git", "add", "-N", "."],
        cwd=str(project_path),
        check=True,
        capture_output=True,
    )


def capture_git_diff(project_path: Path, diff_path: Path) -> None:
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "-c", "core.excludesfile=", "diff", "--binary"],
        cwd=str(project_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr}")
    diff_path.write_text(result.stdout or "", encoding="utf-8")


def diff_metrics(project_path: Path) -> dict:
    """Compute diff metrics excluding build artifacts (Intermediate, Binaries, Saved, DerivedDataCache)."""
    result = subprocess.run(
        ["git", "-c", "core.excludesfile=", "diff", "--numstat"],
        cwd=str(project_path),
        capture_output=True,
        text=True,
    )

    # Exclude UE5 build artifacts and other transient directories
    excluded_prefixes = (
        "Intermediate/",
        "Binaries/",
        "Saved/",
        "DerivedDataCache/",
    )

    files_changed = 0
    lines_added = 0
    lines_deleted = 0
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        a, b, filepath = parts
        # Skip build artifacts and binary files
        if any(filepath.startswith(p) for p in excluded_prefixes):
            continue
        if a == "-" and b == "-":
            continue  # Binary file
        files_changed += 1
        if a != "-":
            lines_added += int(a)
        if b != "-":
            lines_deleted += int(b)
    return {
        "files_changed": files_changed,
        "lines_added": lines_added,
        "lines_deleted": lines_deleted,
    }


def capture_filtered_git_diff(project_path: Path, diff_path: Path) -> None:
    """Capture a diff excluding UE5 build artifacts."""
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "git", "-c", "core.excludesfile=", "diff", "--binary",
            "--", ".",
            ":(exclude)Intermediate/*", ":(exclude)Binaries/*",
            ":(exclude)Saved/*", ":(exclude)DerivedDataCache/*",
        ],
        cwd=str(project_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr}")
    diff_path.write_text(result.stdout or "", encoding="utf-8")


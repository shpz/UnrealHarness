"""Uninstall UnrealHarness skills from AI assistant skills directories.

Removes skills that match this project's skills/ folder from the target
AI assistant's skills directory.

Examples:
    python scripts/uninstall.py
        Uninstall from all detected assistants (with confirmation).

    python scripts/uninstall.py --assistant claude --force
        Remove from Claude Code without prompting.
"""
from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"

ASSISTANTS: dict[str, dict[str, Path | str]] = {
    "claude": {"name": "Claude Code", "path": Path.home() / ".claude" / "skills"},
    "opencode": {"name": "OpenCode", "path": Path.home() / ".opencode" / "skills"},
    "codex": {"name": "Codex", "path": Path.home() / ".codex" / "skills"},
    "kimi": {"name": "Kimi Code", "path": Path.home() / ".kimi" / "skills"},
}


@dataclass(frozen=True)
class RemovalItem:
    assistant: str
    skill: str
    path: Path


def is_reparse_point(path: Path) -> bool:
    """True for symlinks and Windows junctions."""
    if path.is_symlink():
        return True
    if sys.platform == "win32":
        try:
            attrs = os.lstat(path).st_file_attributes
        except OSError:
            return False
        return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    return False


def remove_skill(path: Path) -> None:
    if is_reparse_point(path):
        path.unlink()
    else:
        shutil.rmtree(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Uninstall UnrealHarness skills from AI assistant skills directories."
    )
    parser.add_argument(
        "--assistant",
        choices=[*ASSISTANTS, "all"],
        default="all",
        help="Target AI assistant (default: all)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt.",
    )
    args = parser.parse_args()

    if not SKILLS_DIR.is_dir():
        print(f"Skills source directory not found: {SKILLS_DIR}", file=sys.stderr)
        return 1

    skills = sorted(p.name for p in SKILLS_DIR.iterdir() if p.is_dir())
    if not skills:
        print(f"No skills found in: {SKILLS_DIR}", file=sys.stderr)
        return 1

    targets = list(ASSISTANTS) if args.assistant == "all" else [args.assistant]
    to_remove: list[RemovalItem] = []

    for key in targets:
        name = str(ASSISTANTS[key]["name"])
        dest = Path(ASSISTANTS[key]["path"])
        if not dest.exists():
            print(f"[{name}] not detected, skipping")
            continue

        for skill in skills:
            skill_path = dest / skill
            if skill_path.exists() or is_reparse_point(skill_path):
                to_remove.append(RemovalItem(assistant=name, skill=skill, path=skill_path))

    if not to_remove:
        print("No matching skills found to uninstall.")
        return 0

    print("The following will be removed:")
    for item in to_remove:
        print(f"  [{item.assistant}] {item.skill}")

    if not args.force:
        confirm = input("Proceed? (y/N) ")
        if confirm.strip().lower() != "y":
            print("Aborted.")
            return 0

    for item in to_remove:
        remove_skill(item.path)
        print(f"Removed [{item.assistant}] {item.skill}")

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

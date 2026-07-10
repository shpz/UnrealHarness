"""Install UnrealHarness skills into AI assistant skills directories.

Scans the project skills/ folder and copies or symlinks each skill
to the target AI assistant's skills directory.
Supports Claude Code, OpenCode, Codex, and Kimi Code.

Examples:
    python scripts/install.py
        Install to all detected assistants.

    python scripts/install.py --assistant claude --link
        Symlink to Claude Code only (useful for development).
"""
from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
import tempfile
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"

ASSISTANTS: dict[str, dict[str, Path | str]] = {
    "claude": {"name": "Claude Code", "path": Path.home() / ".claude" / "skills"},
    "opencode": {"name": "OpenCode", "path": Path.home() / ".opencode" / "skills"},
    "codex": {"name": "Codex", "path": Path.home() / ".codex" / "skills"},
    "kimi": {"name": "Kimi Code", "path": Path.home() / ".kimi" / "skills"},
}


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


def remove_existing(path: Path) -> None:
    if is_reparse_point(path):
        path.unlink()
    else:
        shutil.rmtree(path)


def check_symlink_permission() -> str | None:
    """Return None if symlinks can be created, else the error message."""
    test_root = Path(tempfile.gettempdir()) / f"UnrealHarness-LinkTest-{uuid.uuid4().hex}"
    try:
        target = test_root / "target"
        target.mkdir(parents=True)
        (test_root / "link").symlink_to(target, target_is_directory=True)
        return None
    except OSError as e:
        return str(e)
    finally:
        shutil.rmtree(test_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install UnrealHarness skills into AI assistant skills directories."
    )
    parser.add_argument(
        "--assistant",
        choices=[*ASSISTANTS, "all"],
        default="all",
        help="Target AI assistant (default: all)",
    )
    parser.add_argument(
        "--link",
        action="store_true",
        help="Create symbolic links instead of copying files. Useful for development.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing skill directories.",
    )
    args = parser.parse_args()

    if not SKILLS_DIR.is_dir():
        print(f"Skills source directory not found: {SKILLS_DIR}", file=sys.stderr)
        return 1

    skills = sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())
    if not skills:
        print(f"No skills found in: {SKILLS_DIR}", file=sys.stderr)
        return 1

    print(f"Found {len(skills)} skill(s):")
    for skill in skills:
        print(f"  - {skill.name}")
    print()

    if args.link:
        error = check_symlink_permission()
        if error is not None:
            print(
                "Cannot create symbolic links. Re-run as Administrator or enable "
                f"Windows Developer Mode, then retry with --link. Original error: {error}",
                file=sys.stderr,
            )
            return 1

    targets = list(ASSISTANTS) if args.assistant == "all" else [args.assistant]
    installed_any = False
    skipped_any = False

    for key in targets:
        name = ASSISTANTS[key]["name"]
        dest = Path(ASSISTANTS[key]["path"])

        if not dest.exists():
            if not dest.parent.exists():
                print(f"[{name}] not detected, skipping")
                continue
            dest.mkdir(parents=True, exist_ok=True)

        print(f"[{name}] installing to: {dest}")

        for skill in skills:
            dst_path = dest / skill.name

            if dst_path.exists() or is_reparse_point(dst_path):
                if not args.force:
                    print(f"  skip {skill.name} (exists, use --force to overwrite)")
                    skipped_any = True
                    continue
                remove_existing(dst_path)

            if args.link:
                dst_path.symlink_to(skill, target_is_directory=True)
                print(f"  link {skill.name} -> {skill}")
            else:
                shutil.copytree(skill, dst_path)
                print(f"  copy {skill.name}")

            installed_any = True

        print()

    if not installed_any:
        if skipped_any:
            print("All matching skills are already installed. Use --force to overwrite.")
            return 0
        print(
            "Nothing was installed. Make sure the target assistant is installed "
            "or use --assistant.",
            file=sys.stderr,
        )
        return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

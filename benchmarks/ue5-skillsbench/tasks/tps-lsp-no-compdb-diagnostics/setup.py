"""Setup for LSP no-compdb trap task.

Guarantees the trap condition inside this trial workspace. Engine-root state
belongs to the shared installation and is never removed or overwritten.
"""
import sys
from pathlib import Path


TARGET_HEADER = Path("Source/TPSample/TPSampleCharacter.h")


def remove_if_exists(path: Path, removed: list[str]) -> None:
    if path.exists():
        path.unlink()
        removed.append(str(path))


def main() -> int:
    project_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".").resolve()

    removed: list[str] = []
    for name in ["compile_commands.json", ".clangd"]:
        remove_if_exists(project_path / name, removed)

    uproject = project_path / "TPSample.uproject"
    if not uproject.exists():
        print(f"uproject missing: {uproject}", file=sys.stderr)
        return 1

    print(f"Removed: {removed if removed else 'nothing (already clean)'}")

    header = project_path / TARGET_HEADER
    if not header.exists():
        print(f"Target header missing: {header}", file=sys.stderr)
        return 1

    print(f"Target header present: {header}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Setup for LSP no-compdb trap task.

Guarantees the trap condition: no compile database and no .clangd config
anywhere clangd could pick them up. This covers the workspace project root
AND the engine root, because UBT GenerateClangDatabase writes
compile_commands.json to the engine installation directory on some UE
versions, and a previous trial's leftover would defuse the trap.
"""
import re
import subprocess
import sys
from pathlib import Path


TARGET_HEADER = Path("Source/TPSample/TPSampleCharacter.h")


def read_engine_association(uproject: Path) -> str | None:
    match = re.search(r'"EngineAssociation"\s*:\s*"([^"]+)"', uproject.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def resolve_engine_root(uproject: Path) -> Path | None:
    association = read_engine_association(uproject)
    if not association or sys.platform != "win32":
        return None

    if re.match(r"^\d+\.\d+", association):
        key = rf"HKLM\SOFTWARE\EpicGames\Unreal Engine\{association}"
        value_name = "InstalledDirectory"
    else:
        key = rf"HKCU\SOFTWARE\Epic Games\Unreal Engine\Builds\{association}"
        value_name = "Path"

    try:
        result = subprocess.run(
            ["reg", "query", key, "/v", value_name],
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
        if stripped.startswith(value_name):
            parts = re.split(r"\s+", stripped, maxsplit=2)
            if len(parts) == 3:
                candidate = Path(parts[2])
                if candidate.exists():
                    return candidate
    return None


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

    engine_root = resolve_engine_root(uproject)
    if engine_root is not None:
        # Only the generated compdb; never touch actual engine files.
        remove_if_exists(engine_root / "compile_commands.json", removed)
        print(f"Engine root checked: {engine_root}")
    else:
        print("Warning: engine root could not be resolved; leftover engine-root compile_commands.json may defuse the trap", file=sys.stderr)

    print(f"Removed: {removed if removed else 'nothing (already clean)'}")

    header = project_path / TARGET_HEADER
    if not header.exists():
        print(f"Target header missing: {header}", file=sys.stderr)
        return 1

    print(f"Target header present: {header}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

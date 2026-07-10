"""Setup for the mixed LSP audit task.

1. Refuses to run if fixtures/answer key do not match certification.json
   (stale ground truth) or if the engine version differs from the certified one.
2. Injects the five Bench fixture classes into the workspace project.
3. Restores the trap condition: no compile database or .clangd anywhere
   clangd could pick them up (project root and engine root).
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TASK_DIR / "fixtures" / "Bench"
ANSWER_KEY_PATH = TASK_DIR / "answer_key.json"
CERTIFICATION_PATH = TASK_DIR / "certification.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def load_certification() -> dict[str, object]:
    return json.loads(CERTIFICATION_PATH.read_text(encoding="utf-8"))


def certified_fixture_names(certification: dict[str, object]) -> dict[str, str]:
    fingerprints = certification["fixture_sha256"]
    assert isinstance(fingerprints, dict)
    return fingerprints


def verify_certification(uproject: Path) -> dict[str, object]:
    if not CERTIFICATION_PATH.exists():
        print("certification.json missing; run certify.py first", file=sys.stderr)
        sys.exit(1)

    certification = load_certification()

    if certification["answer_key_sha256"] != sha256(ANSWER_KEY_PATH):
        print("answer_key.json changed since certification; re-run certify.py", file=sys.stderr)
        sys.exit(1)

    for name, expected in certified_fixture_names(certification).items():
        fixture = FIXTURES_DIR / name
        if not fixture.exists():
            print(f"fixture missing: {name}", file=sys.stderr)
            sys.exit(1)
        if sha256(fixture) != expected:
            print(f"fixture changed since certification: {name}; re-run certify.py", file=sys.stderr)
            sys.exit(1)

    workspace_association = read_engine_association(uproject)
    if workspace_association != certification["engine_association"]:
        print(
            f"engine mismatch: certified for {certification['engine_association']}, "
            f"workspace uses {workspace_association}; re-run certify.py",
            file=sys.stderr,
        )
        sys.exit(1)

    return certification


def remove_if_exists(path: Path, removed: list[str]) -> None:
    if path.exists():
        path.unlink()
        removed.append(str(path))


def main() -> int:
    project_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".").resolve()

    uproject = project_path / "TPSample.uproject"
    if not uproject.exists():
        print(f"uproject missing: {uproject}", file=sys.stderr)
        return 1

    certification = verify_certification(uproject)
    print(f"Certification valid (engine {certification['engine_association']}, certified {certification['certified_at']})")

    answer_key = json.loads(ANSWER_KEY_PATH.read_text(encoding="utf-8"))
    target_dir = project_path / answer_key["module_relative_dir"]
    target_dir.mkdir(parents=True, exist_ok=True)
    fixture_names = list(certified_fixture_names(certification))
    for name in fixture_names:
        shutil.copy2(FIXTURES_DIR / name, target_dir / name)
    print(f"Injected {len(fixture_names)} fixture files into {target_dir}")

    removed: list[str] = []
    for name in ["compile_commands.json", ".clangd"]:
        remove_if_exists(project_path / name, removed)

    engine_root = resolve_engine_root(uproject)
    if engine_root is not None:
        remove_if_exists(engine_root / "compile_commands.json", removed)
        print(f"Engine root checked: {engine_root}")
    else:
        print("Warning: engine root could not be resolved; leftover engine-root compile_commands.json may defuse the trap", file=sys.stderr)

    print(f"Removed: {removed if removed else 'nothing (already clean)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

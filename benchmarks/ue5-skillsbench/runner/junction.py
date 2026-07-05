"""Windows directory junction helpers."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def _cmd_create_junction(junction_dir: Path, target: Path) -> None:
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction_dir), str(target)],
        check=True,
        capture_output=True,
    )


def create_junction(junction_dir: Path, target: Path) -> None:
    junction_dir = Path(junction_dir)
    target = Path(target)
    if not target.exists():
        raise FileNotFoundError(f"Junction target does not exist: {target}")
    junction_dir.parent.mkdir(parents=True, exist_ok=True)
    if junction_dir.exists() or junction_dir.is_symlink():
        remove_junction(junction_dir)
    _cmd_create_junction(junction_dir, target)


def remove_junction(junction_dir: Path) -> None:
    junction_dir = Path(junction_dir)
    if not junction_dir.exists():
        return
    if is_junction(junction_dir):
        os.rmdir(junction_dir)
    else:
        shutil.rmtree(junction_dir)


def is_junction(path: Path) -> bool:
    path = Path(path)
    if not path.exists():
        return False
    try:
        import _winapi
        # Reparse point tag 0xA0000003 is IO_REPARSE_TAG_MOUNT_POINT (directory junction)
        return _winapi.GetReparseTag(str(path)) == 0xA0000003
    except AttributeError:
        # Python 3.14 exposes the reparse tag via os.lstat instead of _winapi.GetReparseTag.
        return os.lstat(path).st_reparse_tag == 0xA0000003
    except Exception:
        return False


def resolve_junction_root() -> Path:
    candidates = [
        Path("C:/.kh"),
        Path(tempfile.gettempdir()) / ".kh",
        Path.home() / ".kh",
    ]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            test_file = candidate / ".write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            return candidate
        except OSError:
            continue
    raise RuntimeError("No writable junction root found")

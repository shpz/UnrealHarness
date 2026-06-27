"""Smoke test setup: no modifications needed."""
import sys
from pathlib import Path

if __name__ == "__main__":
    workspace_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    project_path = Path(sys.argv[2]) if len(sys.argv) > 2 else workspace_root / "TPSample"
    print("Smoke test: no setup changes.")

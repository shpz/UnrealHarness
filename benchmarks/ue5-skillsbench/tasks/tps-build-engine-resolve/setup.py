"""Setup: make EngineAssociation fail deterministic registry resolution."""
from __future__ import annotations

import json
from pathlib import Path
import sys


def main() -> None:
    project_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".").resolve()
    uproject_path = project_path / "TPSample.uproject"

    if not uproject_path.exists():
        raise RuntimeError(f".uproject not found: {uproject_path}")

    descriptor = json.loads(uproject_path.read_text(encoding="utf-8"))
    previous = descriptor.get("EngineAssociation", "")
    broken_guid = "00000000-0000-0000-0000-000000000000"
    descriptor["EngineAssociation"] = broken_guid
    uproject_path.write_text(json.dumps(descriptor, indent=2), encoding="utf-8")
    print(f"Changed EngineAssociation from '{previous}' to unregistered GUID '{broken_guid}'")


if __name__ == "__main__":
    main()

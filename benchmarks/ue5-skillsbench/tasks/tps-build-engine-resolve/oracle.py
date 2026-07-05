"""Oracle action for tps-build-engine-resolve."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    uproject_path = Path("TPSample.uproject")
    descriptor = json.loads(uproject_path.read_text(encoding="utf-8"))
    descriptor["EngineAssociation"] = "5.7"
    uproject_path.write_text(json.dumps(descriptor, indent=2), encoding="utf-8")
    print("Restored EngineAssociation to 5.7")


if __name__ == "__main__":
    main()

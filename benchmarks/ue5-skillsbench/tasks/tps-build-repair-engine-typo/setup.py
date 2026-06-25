"""Inject an engine association typo into .uproject to break engine resolution."""
import json
import sys
from pathlib import Path


def main():
    project_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
    uproject_path = project_path / "TPSample.uproject"
    if not uproject_path.exists():
        raise RuntimeError(f".uproject not found: {uproject_path}")

    descriptor = json.loads(uproject_path.read_text(encoding="utf-8"))
    original = descriptor.get("EngineAssociation", "")
    descriptor["EngineAssociation"] = "5.8"  # intentionally wrong
    text = json.dumps(descriptor, indent="\t")
    # Preserve original "no newline at end of file" format
    uproject_path.write_text(text, encoding="utf-8", newline="\n")
    print(f"Changed EngineAssociation from '{original}' to '5.8'")


if __name__ == "__main__":
    main()

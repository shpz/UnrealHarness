"""Setup: Move project into a nested subdirectory and create a decoy empty project."""
import sys
from pathlib import Path
import shutil
import json


def main():
    project_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".").resolve()

    # Create nested directories
    game_a = project_path / "Projects" / "GameA"
    game_b = project_path / "Projects" / "GameB"
    game_a.mkdir(parents=True, exist_ok=True)
    game_b.mkdir(parents=True, exist_ok=True)

    # Move real project files to GameA
    for item in ["Source", "Config", "TPSample.uproject"]:
        src = project_path / item
        if src.exists():
            dst = game_a / item
            if src.is_dir():
                shutil.move(str(src), str(dst))
            else:
                shutil.move(str(src), str(dst))
            print(f"Moved {src} -> {dst}")

    # Create decoy empty project in GameB
    decoy_uproject = {
        "FileVersion": 3,
        "EngineAssociation": "",
        "Category": "",
        "Description": "Decoy project with no source",
        "Modules": []
    }
    (game_b / "TPSample.uproject").write_text(json.dumps(decoy_uproject, indent=2), encoding="utf-8")
    print(f"Created decoy project: {game_b / 'TPSample.uproject'}")

    # Create README hint
    readme = project_path / "README.txt"
    readme.write_text(
        "Project files have been reorganized.\n"
        "The actual project is located under Projects/GameA/.\n"
        "Projects/GameB/ contains an empty decoy project.\n",
        encoding="utf-8",
    )
    print(f"Created README: {readme}")


if __name__ == "__main__":
    main()

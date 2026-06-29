import sys
from pathlib import Path
import shutil
import os


def main():
    project_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".").resolve()

    for dir_name in ["Binaries", "Intermediate"]:
        d = project_path / dir_name
        if d.exists():
            shutil.rmtree(d, onexc=lambda func, path, exc_info: (os.chmod(path, os.stat.S_IWUSR), func(path)))
            print(f"Removed {dir_name} directory: {d}")
        else:
            print(f"{dir_name} directory not found, nothing to remove: {d}")


if __name__ == "__main__":
    main()

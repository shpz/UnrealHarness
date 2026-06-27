import sys
from pathlib import Path
import shutil


def main():
    project_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".").resolve()

    binaries = project_path / "Binaries"
    if binaries.exists():
        shutil.rmtree(binaries, onexc=lambda func, path, exc_info: (os.chmod(path, os.stat.S_IWUSR), func(path)))
        print(f"Removed Binaries directory: {binaries}")
    else:
        print(f"Binaries directory not found, nothing to remove: {binaries}")


if __name__ == "__main__":
    import os
    main()

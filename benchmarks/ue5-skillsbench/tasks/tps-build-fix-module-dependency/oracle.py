"""Oracle action for tps-build-fix-module-dependency."""
from __future__ import annotations

from pathlib import Path


def main() -> None:
    _restore_umg_dependency(Path.cwd())
    print("Restored UMG dependency in TPSample.Build.cs")


def _restore_umg_dependency(project_path: Path) -> None:
    build_cs = project_path / "Source" / "TPSample" / "TPSample.Build.cs"
    text = build_cs.read_text(encoding="utf-8")
    if '"UMG"' in text:
        return

    anchor = '"Engine",'
    if anchor in text:
        text = text.replace(anchor, f'{anchor}\n\t\t\t"UMG",', 1)
    else:
        text = text.replace(
            "PublicDependencyModuleNames.AddRange(new string[] {",
            'PublicDependencyModuleNames.AddRange(new string[] {\n\t\t\t"UMG",',
            1,
        )
    build_cs.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

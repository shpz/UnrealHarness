"""Remove the EnhancedInput dependency required by existing TPSample source."""
from __future__ import annotations

from pathlib import Path


def main() -> None:
    build_cs = Path.cwd() / "Source" / "TPSample" / "TPSample.Build.cs"
    _remove_enhanced_input_dependency(build_cs)


def _remove_enhanced_input_dependency(build_cs: Path) -> None:
    text = build_cs.read_text(encoding="utf-8")
    text = text.replace('\n\t\t\t"EnhancedInput",', "")
    text = text.replace('\n            "EnhancedInput",', "")
    text = text.replace('\n            "EnhancedInput"', "")
    build_cs.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

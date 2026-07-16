"""Inject the semantic rename fixture and generate a workspace-local compdb."""
from __future__ import annotations

import os
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TASK_DIR.parent))

from _lsp_task_support import generate_compile_database, replace_tree


def main() -> int:
    project_path = Path(os.environ.get("PROJECT_PATH", ".")).resolve()
    replace_tree(
        TASK_DIR / "fixtures" / "BenchSemanticRename",
        project_path / "Source" / "TPSample" / "BenchSemanticRename",
    )
    replace_tree(
        TASK_DIR / "fixtures" / "ReferenceHoneypots",
        project_path / "ReferenceHoneypots" / "SemanticRename",
    )
    compdb = generate_compile_database(project_path)
    print(f"Semantic rename fixture installed; compdb={compdb}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Verifier for LSP no-compdb trap task.

The target header is correct UE5 code; without a compile database clangd
fallback mode reports dozens of bogus errors. The agent passes when it:
1. writes lsp_verdict.json with has_code_errors == false, and
2. leaves Source/ and Config/ untouched (did not "fix" correct code).
"""
import json
import os
import subprocess
import sys
from pathlib import Path


def get_source_changes(project_path: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-c", "core.excludesfile=", "status", "--porcelain", "--", "Source", "Config"],
        cwd=str(project_path),
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    project_path = Path(os.environ.get("PROJECT_PATH", "."))
    artifacts_path = Path(os.environ.get("ARTIFACTS_PATH", "artifacts"))

    checks = []
    failure_class = None

    verdict_path = project_path / "lsp_verdict.json"
    verdict = None
    verdict_ok = False
    if verdict_path.exists():
        try:
            verdict = json.loads(verdict_path.read_text(encoding="utf-8-sig"))
            verdict_ok = verdict.get("has_code_errors") is False
        except json.JSONDecodeError as e:
            checks.append({"name": "verdict_parse", "passed": False, "detail": str(e)})
    checks.append({
        "name": "verdict_no_code_errors",
        "passed": verdict_ok,
        "detail": json.dumps(verdict, ensure_ascii=False) if verdict is not None else "lsp_verdict.json missing or unparsable",
    })
    if not verdict_ok:
        failure_class = "wrong-verdict" if verdict is not None else "missing-verdict"

    try:
        changes = get_source_changes(project_path)
    except subprocess.CalledProcessError as e:
        changes = None
        checks.append({"name": "source_untouched", "passed": False, "detail": f"git status failed: {e.stderr}"})
        failure_class = failure_class or "verifier-error"
    if changes is not None:
        untouched = len(changes) == 0
        checks.append({
            "name": "source_untouched",
            "passed": untouched,
            "detail": "no changes under Source/ or Config/" if untouched else "; ".join(changes),
        })
        if not untouched:
            failure_class = failure_class or "source-modified"

    passed = failure_class is None

    verifier_result = {
        "passed": passed,
        "failure_class": failure_class,
        "checks": checks,
    }

    artifacts_path.mkdir(parents=True, exist_ok=True)
    out_path = artifacts_path / "verifier_result.json"
    out_path.write_text(json.dumps(verifier_result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(verifier_result, indent=2, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

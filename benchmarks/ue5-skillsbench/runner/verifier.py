"""Verifier execution wrapper."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional


def run_verifier(
    verifier_script: Path,
    workspace_root: Path,
    project_path: Path,
    artifacts_path: Path,
    benchmark_root: Path,
    timeout_minutes: int = 30,
) -> dict:
    """Run a verifier script (.py or .ps1) and return its result."""
    env = {
        **{k: v for k, v in {
            "WORKSPACE_ROOT": str(workspace_root),
            "PROJECT_PATH": str(project_path),
            "ARTIFACTS_PATH": str(artifacts_path),
            "BENCHMARK_ROOT": str(benchmark_root),
        }.items() if v is not None},
    }

    if verifier_script.suffix == ".py":
        cmd = [sys.executable, str(verifier_script)]
    elif verifier_script.suffix == ".ps1":
        cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(verifier_script)]
    else:
        raise RuntimeError(f"Unsupported verifier script type: {verifier_script}")

    stdout_path = artifacts_path / "verifier.stdout.log"
    stderr_path = artifacts_path / "verifier.stderr.log"

    result = subprocess.run(
        cmd,
        cwd=str(project_path),
        capture_output=True,
        text=True,
        env={**subprocess.os.environ, **env},
        timeout=timeout_minutes * 60,
    )

    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")

    verifier_result_path = artifacts_path / "verifier_result.json"
    verifier_json = None
    if verifier_result_path.exists():
        try:
            verifier_json = json.loads(verifier_result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            verifier_json = {"passed": False, "failureClass": "verifier-error", "error": str(e)}

    return {
        "exit_code": result.returncode,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "verifier_result": verifier_json,
    }

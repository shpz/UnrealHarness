"""Authoritative Automation rerun for task verifiers.

When enabled (runner sets SKILLSBENCH_RERUN_AUTOMATION=1 for real trials),
verifiers rerun the requested Automation scope themselves instead of trusting
report files left in the workspace. Unit tests and engine-less environments
leave the flag unset and fall back to artifact parsing plus editor-log
evidence.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

try:
    from .automation_report import AutomationReportResult, parse_automation_report_dir
except ImportError:  # loaded flat via sys.path by task verifiers
    from automation_report import AutomationReportResult, parse_automation_report_dir


RERUN_ENV = "SKILLSBENCH_RERUN_AUTOMATION"
_RERUN_DIR_NAME = "VerifierRerun"


def rerun_enabled() -> bool:
    return os.environ.get(RERUN_ENV, "").strip().lower() in {"1", "true", "yes"}


def _sanitize_label(label: str) -> str:
    return re.sub(r'[<>?:"/\\|*+ ]', "_", label)


def run_authoritative_automation(
    project_path: Path,
    test_filter: str,
    label: str | None = None,
    uproject_name: str = "TPSample.uproject",
) -> AutomationReportResult | None:
    """Rerun the scope headlessly and parse only the fresh report directory.

    Returns None when reruns are disabled so callers can fall back to
    artifact-based verification.
    """
    if not rerun_enabled():
        return None

    try:
        from .unreal import invoke_automation
    except ImportError:
        from unreal import invoke_automation

    automation_dir = (
        project_path
        / "Saved"
        / "Automation"
        / "Reports"
        / "Raw"
        / f"{_RERUN_DIR_NAME}_{_sanitize_label(label or test_filter)}"
    )
    _ = invoke_automation(
        project_path=project_path,
        test_filter=test_filter,
        automation_dir=automation_dir,
        uproject_name=uproject_name,
    )
    return parse_automation_report_dir(automation_dir)

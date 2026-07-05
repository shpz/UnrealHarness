"""Shared verifier result schema helpers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def make_result(
    passed: bool,
    failure_class: str | None,
    checks: list[dict[str, Any]],
    build: dict[str, Any] | None = None,
    automation: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "passed": passed,
        "failure_class": failure_class,
        "checks": checks,
    }
    if build is not None:
        result["build"] = build
    if automation is not None:
        result["automation"] = automation
    if artifacts is not None:
        result["artifacts"] = artifacts
    result.update(extra)
    return result


def validate_result_schema(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(result, dict):
        return ["verifier result must be a JSON object"]

    if "passed" not in result:
        errors.append("missing required field: passed")
    elif not isinstance(result["passed"], bool):
        errors.append("passed must be a boolean")

    if "failure_class" not in result:
        errors.append("missing required field: failure_class")
    elif result["failure_class"] is not None and not isinstance(result["failure_class"], str):
        errors.append("failure_class must be a string or null")

    if "checks" not in result:
        errors.append("missing required field: checks")
    elif not isinstance(result["checks"], list):
        errors.append("checks must be a list")
    else:
        for index, check in enumerate(result["checks"]):
            if not isinstance(check, dict):
                errors.append(f"checks[{index}] must be an object")
                continue
            if "name" in check and not isinstance(check["name"], str):
                errors.append(f"checks[{index}].name must be a string")
            if "passed" in check and not isinstance(check["passed"], bool):
                errors.append(f"checks[{index}].passed must be a boolean")

    return errors


def write_result(path: Path, result: dict[str, Any]) -> None:
    errors = validate_result_schema(result)
    if errors:
        raise ValueError("Invalid verifier result schema: " + "; ".join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

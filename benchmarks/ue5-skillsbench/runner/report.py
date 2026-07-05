"""Report generation: JSON, Markdown summaries, and failure details."""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from statistics import median
from typing import Any


def load_results(run_root: Path, run_id_prefix: str) -> list[dict]:
    results = []
    if not run_root.exists():
        return results
    for run_dir in sorted(run_root.iterdir()):
        if run_dir.name.startswith(run_id_prefix):
            result_path = run_dir / "result.json"
            if result_path.exists():
                results.append(json.loads(result_path.read_text(encoding="utf-8")))
    return results


def make_report(run_root: Path, run_id: str, output_dir: Path) -> dict:
    results = load_results(run_root, run_id)
    if not results:
        raise RuntimeError(f"No results found for run id prefix '{run_id}'")

    rows = _summarize_results(results)
    failures = _failure_details(results)
    skill_impact = _skill_impact(rows)

    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_id": run_id,
        "result_count": len(results),
        "results": results,
        "summary": rows,
        "skill_impact": skill_impact,
        "failures": failures,
    }

    json_path = output_dir / f"{run_id}-results.json"
    json_path.write_text(json.dumps(summary, indent=4, ensure_ascii=False), encoding="utf-8")

    md_path = output_dir / f"{run_id}-summary.md"
    md_path.write_text(_summary_markdown(run_id, rows, skill_impact), encoding="utf-8")

    failures_path = output_dir / f"{run_id}-failures.md"
    failures_path.write_text(_failures_markdown(run_id, failures), encoding="utf-8")

    return {
        "json_path": str(json_path),
        "md_path": str(md_path),
        "failures_path": str(failures_path),
        "result_count": len(results),
    }


def _summarize_results(results: list[dict]) -> list[dict]:
    rows = []
    by_task: dict[str, list[dict]] = defaultdict(list)
    for result in results:
        by_task[result["task_id"]].append(result)

    for task_id, task_results in sorted(by_task.items()):
        by_condition: dict[str, list[dict]] = defaultdict(list)
        for result in task_results:
            by_condition[result["condition"]].append(result)

        condition_summaries = {
            condition: _summarize_condition(task_id, condition, cond_results)
            for condition, cond_results in sorted(by_condition.items())
        }
        baseline = condition_summaries.get("no-skills")
        for condition, summary in condition_summaries.items():
            summary.update(_compare_to_baseline(summary, baseline, condition))
            rows.append(summary)
    return rows


def _summarize_condition(task_id: str, condition: str, results: list[dict]) -> dict:
    trials = len(results)
    passed = sum(1 for result in results if result.get("overall_passed", False))
    wall_clocks = _metric_values(results, "wall_clock_seconds")
    build_durations = _metric_values(results, "build_duration_seconds")
    agent_durations = [
        float(result["agent"]["duration_seconds"])
        for result in results
        if result.get("agent", {}).get("duration_seconds") is not None
    ]
    files_changed = _metric_values(results, "files_changed")
    lines_changed = [
        float((result.get("metrics", {}).get("lines_added") or 0) + (result.get("metrics", {}).get("lines_deleted") or 0))
        for result in results
    ]

    failure_classes: dict[str, int] = defaultdict(int)
    for result in results:
        if not result.get("overall_passed", False):
            failure_classes[_result_failure_class(result)] += 1

    skills = sorted({
        skill.get("name")
        for result in results
        for skill in result.get("skills_injected", [])
        if skill.get("name")
    })

    return {
        "task_id": task_id,
        "condition": condition,
        "skills": skills,
        "trials": trials,
        "passed": passed,
        "pass_rate": round(passed / trials, 4) if trials else 0.0,
        "mean_wall_clock_seconds": _mean(wall_clocks),
        "median_wall_clock_seconds": _median(wall_clocks),
        "mean_build_duration_seconds": _mean(build_durations),
        "median_build_duration_seconds": _median(build_durations),
        "mean_agent_duration_seconds": _mean(agent_durations),
        "median_agent_duration_seconds": _median(agent_durations),
        "mean_files_changed": _mean(files_changed),
        "mean_lines_changed": _mean(lines_changed),
        "failure_classes": dict(sorted(failure_classes.items())),
    }


def _compare_to_baseline(summary: dict, baseline: dict | None, condition: str) -> dict:
    if condition == "no-skills" or not baseline:
        return {"delta_pp": None, "normalized_gain": None}
    baseline_rate = baseline["pass_rate"]
    condition_rate = summary["pass_rate"]
    delta = condition_rate - baseline_rate
    normalized = None
    if baseline_rate < 1.0:
        normalized = round(delta / (1.0 - baseline_rate), 4)
    return {
        "delta_pp": round(delta * 100, 2),
        "normalized_gain": normalized,
    }


def _skill_impact(rows: list[dict]) -> dict[str, dict]:
    by_skill: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["delta_pp"] is None:
            continue
        for skill in row.get("skills", []):
            by_skill[skill].append(row)

    impact = {}
    for skill, skill_rows in sorted(by_skill.items()):
        deltas = [row["delta_pp"] for row in skill_rows if row["delta_pp"] is not None]
        gains = [row["normalized_gain"] for row in skill_rows if row["normalized_gain"] is not None]
        negative = [row for row in skill_rows if row["delta_pp"] is not None and row["delta_pp"] < 0]
        failure_classes: dict[str, int] = defaultdict(int)
        for row in skill_rows:
            for failure_class, count in row["failure_classes"].items():
                failure_classes[failure_class] += count
        impact[skill] = {
            "task_count": len({row["task_id"] for row in skill_rows}),
            "condition_count": len(skill_rows),
            "mean_delta_pp": _mean(deltas),
            "mean_normalized_gain": _mean(gains),
            "negative_transfer_count": len(negative),
            "failure_classes": dict(sorted(failure_classes.items())),
        }
    return impact


def _failure_details(results: list[dict]) -> list[dict]:
    failures = []
    for result in results:
        if result.get("overall_passed", False):
            continue
        verifier_result = _read_verifier_result(result)
        failed_checks = [
            {
                "name": check.get("name", f"check-{index}"),
                "details": check.get("details") or check.get("detail"),
            }
            for index, check in enumerate(verifier_result.get("checks", []))
            if check.get("passed") is False
        ]
        failures.append({
            "run_id": result.get("run_id"),
            "task_id": result.get("task_id"),
            "condition": result.get("condition"),
            "trial": result.get("trial"),
            "failure_class": _result_failure_class(result),
            "failed_checks": failed_checks,
            "artifacts": result.get("artifacts", {}),
        })
    return failures


def _read_verifier_result(result: dict) -> dict:
    verifier_path = result.get("artifacts", {}).get("verifier_result")
    if not verifier_path:
        return {}
    path = Path(verifier_path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _summary_markdown(run_id: str, rows: list[dict], skill_impact: dict[str, dict]) -> str:
    lines = [
        "# UE5 SkillsBench Report",
        "",
        f"Run ID prefix: `{run_id}`",
        "",
        "## Condition Summary",
        "",
        "| Task | Condition | Trials | Passed | Pass Rate | Delta pp | Normalized Gain | Mean Wall | Median Wall | Mean Build | Files Changed | Lines Changed | Failures |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        failures = ", ".join(f"{name}:{count}" for name, count in row["failure_classes"].items())
        lines.append(
            "| {task_id} | {condition} | {trials} | {passed} | {pass_rate} | {delta} | {gain} | {mean_wall} | {median_wall} | {mean_build} | {files} | {lines_changed} | {failures} |".format(
                task_id=row["task_id"],
                condition=row["condition"],
                trials=row["trials"],
                passed=row["passed"],
                pass_rate=row["pass_rate"],
                delta=_display(row["delta_pp"]),
                gain=_display(row["normalized_gain"]),
                mean_wall=_display(row["mean_wall_clock_seconds"]),
                median_wall=_display(row["median_wall_clock_seconds"]),
                mean_build=_display(row["mean_build_duration_seconds"]),
                files=_display(row["mean_files_changed"]),
                lines_changed=_display(row["mean_lines_changed"]),
                failures=failures,
            )
        )

    lines.extend([
        "",
        "## Skill Impact",
        "",
        "| Skill | Tasks | Conditions | Mean Delta pp | Mean Normalized Gain | Negative Transfers | Failure Classes |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ])
    for skill, impact in skill_impact.items():
        failures = ", ".join(f"{name}:{count}" for name, count in impact["failure_classes"].items())
        lines.append(
            f"| {skill} | {impact['task_count']} | {impact['condition_count']} | {_display(impact['mean_delta_pp'])} | {_display(impact['mean_normalized_gain'])} | {impact['negative_transfer_count']} | {failures} |"
        )
    if not skill_impact:
        lines.append("| none | 0 | 0 |  |  | 0 |  |")
    lines.extend(["", "Trial artifacts are under `.bench/runs/<run-id>/`."])
    return "\n".join(lines)


def _failures_markdown(run_id: str, failures: list[dict]) -> str:
    lines = [
        "# UE5 SkillsBench Failures",
        "",
        f"Run ID prefix: `{run_id}`",
        "",
    ]
    if not failures:
        lines.append("No failed trials.")
        return "\n".join(lines)

    for failure in failures:
        lines.extend([
            f"## {failure['run_id']}",
            "",
            f"- Task: `{failure['task_id']}`",
            f"- Condition: `{failure['condition']}`",
            f"- Trial: `{failure['trial']}`",
            f"- Failure class: `{failure['failure_class']}`",
            f"- Diff: `{failure.get('artifacts', {}).get('diff', '')}`",
            f"- Verifier result: `{failure.get('artifacts', {}).get('verifier_result', '')}`",
            "",
            "Failed checks:",
        ])
        if failure["failed_checks"]:
            for check in failure["failed_checks"]:
                detail = f" - {check['details']}" if check.get("details") else ""
                lines.append(f"- `{check['name']}`{detail}")
        else:
            lines.append("- No structured failed checks captured.")
        lines.append("")
    return "\n".join(lines)


def _metric_values(results: list[dict], name: str) -> list[float]:
    values = []
    for result in results:
        value = result.get("metrics", {}).get(name)
        if value is not None:
            values.append(float(value))
    return values


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _median(values: list[float]) -> float | None:
    return round(float(median(values)), 3) if values else None


def _display(value: Any) -> Any:
    return "" if value is None else value


def _result_failure_class(result: dict) -> str:
    return (
        result.get("failure_class")
        or result.get("verifier", {}).get("failure_class")
        or result.get("agent", {}).get("failure_class")
        or "unknown"
    )

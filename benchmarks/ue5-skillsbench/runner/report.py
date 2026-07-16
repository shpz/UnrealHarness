"""Report generation: JSON and Markdown summaries."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_results(run_root: Path, run_id_prefix: str) -> list[dict]:
    results = []
    if not run_root.exists():
        return results
    for run_dir in run_root.iterdir():
        if run_dir.name.startswith(run_id_prefix):
            result_path = run_dir / "result.json"
            if result_path.exists():
                results.append(json.loads(result_path.read_text(encoding="utf-8")))
    return results


def make_report(run_root: Path, run_id: str, output_dir: Path) -> dict:
    results = load_results(run_root, run_id)
    if not results:
        raise RuntimeError(f"No results found for run id prefix '{run_id}'")

    from collections import defaultdict

    rows = []
    by_task = defaultdict(list)
    for r in results:
        by_task[r["task_id"]].append(r)

    for task_id, task_results in by_task.items():
        by_condition = defaultdict(list)
        for r in task_results:
            by_condition[r["condition"]].append(r)

        condition_summaries = {}
        for condition, cond_results in by_condition.items():
            trials = len(cond_results)
            passed = sum(1 for r in cond_results if r.get("overall_passed", False))
            pass_rate = passed / trials if trials > 0 else 0.0

            wall_clocks = [r["metrics"]["wall_clock_seconds"] for r in cond_results if r["metrics"].get("wall_clock_seconds") is not None]
            build_durations = [r["metrics"]["build_duration_seconds"] for r in cond_results if r["metrics"].get("build_duration_seconds") is not None]
            agent_durations = [r["agent"]["duration_seconds"] for r in cond_results if r["agent"].get("duration_seconds") is not None]
            semantic_query_counts = [int((r.get("lsp") or {}).get("semantic_query_count", 0)) for r in cond_results]
            lsp_trial_count = sum(1 for count in semantic_query_counts if count > 0)
            failed_query_count = sum(int((r.get("lsp") or {}).get("failed_query_count", 0)) for r in cond_results)
            possibly_incomplete_count = sum(int((r.get("lsp") or {}).get("possibly_incomplete_count", 0)) for r in cond_results)

            failure_classes = defaultdict(int)
            for r in cond_results:
                if not r.get("overall_passed", False):
                    fc = r.get("verifier", {}).get("failure_class") or r.get("agent", {}).get("failure_class") or "unknown"
                    failure_classes[fc] += 1

            condition_summaries[condition] = {
                "task_id": task_id,
                "condition": condition,
                "trials": trials,
                "passed": passed,
                "pass_rate": round(pass_rate, 4),
                "mean_wall_clock_seconds": round(sum(wall_clocks) / len(wall_clocks), 3) if wall_clocks else None,
                "mean_build_duration_seconds": round(sum(build_durations) / len(build_durations), 3) if build_durations else None,
                "mean_agent_duration_seconds": round(sum(agent_durations) / len(agent_durations), 3) if agent_durations else None,
                "mean_semantic_query_count": round(sum(semantic_query_counts) / trials, 3) if trials else 0.0,
                "lsp_trial_count": lsp_trial_count,
                "failed_query_count": failed_query_count,
                "possibly_incomplete_count": possibly_incomplete_count,
                "skill_usage_confidence": "evidence-based-partial" if lsp_trial_count else "partial",
                "failure_classes": dict(failure_classes),
            }

        no_skills = condition_summaries.get("no-skills")
        if task_id.startswith("tps-lsp-"):
            skills_cond = condition_summaries.get("ue-lsp-only") or condition_summaries.get("all-ue-skills")
        else:
            skills_cond = condition_summaries.get("ue-build-only") or condition_summaries.get("all-ue-skills")
        delta_pp = None
        normalized_gain = None
        agent_duration_delta_seconds = None
        if no_skills and skills_cond:
            ns_rate = no_skills["pass_rate"]
            sk_rate = skills_cond["pass_rate"]
            delta_pp = round((sk_rate - ns_rate) * 100, 2)
            if ns_rate < 1.0:
                normalized_gain = round((sk_rate - ns_rate) / (1.0 - ns_rate), 4)
            if no_skills["mean_agent_duration_seconds"] is not None and skills_cond["mean_agent_duration_seconds"] is not None:
                agent_duration_delta_seconds = round(
                    skills_cond["mean_agent_duration_seconds"] - no_skills["mean_agent_duration_seconds"], 3
                )

        for cs in condition_summaries.values():
            rows.append({
                **cs,
                "delta_pp": delta_pp,
                "normalized_gain": normalized_gain,
                "agent_duration_delta_seconds": agent_duration_delta_seconds,
            })

    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_id": run_id,
        "result_count": len(results),
        "results": results,
        "summary": rows,
    }

    json_path = output_dir / f"{run_id}-results.json"
    json_path.write_text(json.dumps(summary, indent=4, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        "# UE5 SkillsBench 测试报告",
        "",
        f"运行 ID 前缀：`{run_id}`",
        "",
        "| 任务 | 条件 | 试次数 | 通过数 | 通过率 | 对照差值百分点 | 归一化增益 | 平均 Wall Clock（秒） | 平均 Build（秒） | 平均 Agent（秒） | Agent 时长差（秒） | 平均语义查询数 | 使用 LSP 的 trial | 查询失败 | 可能不完整 | 使用证据置信度 | 失败分类 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for r in rows:
        fc = r["failure_classes"]
        fc_str = ", ".join(f"{k}:{v}" for k, v in fc.items()) if fc else ""
        delta = "不适用" if r["delta_pp"] is None else r["delta_pp"]
        norm = "不适用" if r["normalized_gain"] is None else r["normalized_gain"]
        wc = r["mean_wall_clock_seconds"] if r["mean_wall_clock_seconds"] is not None else ""
        bd = r["mean_build_duration_seconds"] if r["mean_build_duration_seconds"] is not None else ""
        ad = r["mean_agent_duration_seconds"] if r["mean_agent_duration_seconds"] is not None else ""
        duration_delta = "不适用" if r["agent_duration_delta_seconds"] is None else r["agent_duration_delta_seconds"]
        md_lines.append(
            f"| {r['task_id']} | {r['condition']} | {r['trials']} | {r['passed']} | {r['pass_rate']} | {delta} | {norm} | {wc} | {bd} | {ad} | {duration_delta} | {r['mean_semantic_query_count']} | {r['lsp_trial_count']} | {r['failed_query_count']} | {r['possibly_incomplete_count']} | {r['skill_usage_confidence']} | {fc_str} |"
        )
    md_lines.append("")
    md_lines.append("所有 trial 产物位于 `.bench/runs/<run-id>/`。")
    md_lines.append("LSP trace 是可观测的调用证据，但不能证明 agent 的全部推理来源，因此 skill usage confidence 仍为 partial/evidence-based-partial。")

    md_path = output_dir / f"{run_id}-summary.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    return {
        "json_path": str(json_path),
        "md_path": str(md_path),
        "result_count": len(results),
    }

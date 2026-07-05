"""CLI entry point for the benchmark runner."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from .adapter import CodexAdapter, KimiCodeAdapter, ManualAdapter, NoopAdapter, OracleAdapter
from .automation_artifacts import collect_automation_artifacts
from .config import BenchmarkConfig, ConditionConfig, TaskConfig, discover_tasks, load_benchmark_yaml, load_task_toml
from .metrics import capture_filtered_git_diff, capture_git_diff, diff_metrics, git_add_untracked
from .preflight import run_preflight
from .report import make_report
from .unreal import invoke_build
from .verifier import run_verifier
from .workspace import prepare_workspace


def _repo_root() -> Path:
    # runner is at benchmarks/ue5-skillsbench/runner/
    return Path(__file__).resolve().parents[3]


def _benchmark_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _run_id_now() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def select_matrix_tasks(
    tasks: list[TaskConfig],
    task_ids: list[str] | None = None,
    task_filters: list[str] | None = None,
) -> list[TaskConfig]:
    task_ids = task_ids or []
    task_filters = task_filters or []
    by_id = {task.id: task for task in tasks}

    if task_ids:
        missing = [task_id for task_id in task_ids if task_id not in by_id]
        if missing:
            raise RuntimeError(f"Unknown task id(s): {', '.join(missing)}")
        selected = [by_id[task_id] for task_id in task_ids]
    else:
        selected = [task for task in tasks if task.benchmark_role == "formal"]

    if task_filters:
        filter_set = set(task_filters)
        selected = [
            task for task in selected
            if task.metadata.subcategory in filter_set or any(tag in filter_set for tag in task.metadata.tags)
        ]

    return selected


def select_matrix_conditions(
    conditions: list[ConditionConfig],
    condition_ids: list[str] | None = None,
) -> list[ConditionConfig]:
    condition_ids = condition_ids or []
    by_id = {condition.id: condition for condition in conditions}
    if not condition_ids:
        return conditions
    missing = [condition_id for condition_id in condition_ids if condition_id not in by_id]
    if missing:
        raise RuntimeError(f"Unknown condition id(s): {', '.join(missing)}")
    return [by_id[condition_id] for condition_id in condition_ids]


def validate_task_oracle_contract(task: TaskConfig, task_dir: Path) -> list[str]:
    errors: list[str] = []
    if task.benchmark_role == "smoke":
        if task.oracle.type != "none":
            errors.append("smoke tasks must use [oracle].type = \"none\"")
        return errors

    if task.benchmark_role != "formal":
        errors.append(f"unknown benchmark_role: {task.benchmark_role}")
        return errors

    if task.oracle.type not in {"patch", "action"}:
        errors.append("formal tasks must use [oracle].type = \"patch\" or \"action\"")
        return errors

    if not task.oracle.path:
        errors.append("formal tasks must declare [oracle].path")
        return errors

    oracle_path = task_dir / task.oracle.path
    if not oracle_path.exists():
        errors.append(f"oracle file does not exist: {oracle_path}")
    return errors


def describe_skill_injection(
    repo_root: Path,
    workspace_root: Path,
    config: BenchmarkConfig,
    condition: ConditionConfig,
    skills_root: Path | None,
) -> dict:
    skill_paths = {skill.name: skill.path for skill in config.skills}
    injected = []
    for skill_name in condition.skills:
        source = repo_root / skill_paths.get(skill_name, f"skills/{skill_name}")
        destination = (skills_root or workspace_root / "skills") / skill_name
        injected.append({
            "name": skill_name,
            "source": str(source),
            "destination": str(destination),
        })
    return {
        "skills_injected": injected,
        "skills_root": str(skills_root) if skills_root else None,
        "skills_root_exists": bool(skills_root and skills_root.exists()),
    }


def duration_seconds_or_zero(metric: dict | None) -> float:
    if not metric:
        return 0.0
    value = metric.get("duration_seconds")
    return float(value) if value is not None else 0.0


def matrix_trial_run_id(run_id: str, sequence: int) -> str:
    return f"{run_id}-r{sequence:03d}"


def validation_trial_run_id(run_id: str, phase: str, trial: int, max_length: int = 40) -> str:
    phase_codes = {
        "initial": "vi",
        "oracle": "vo",
    }
    if phase not in phase_codes:
        raise ValueError(f"Unknown validation phase: {phase}")

    suffix = f"{phase_codes[phase]}{trial:03d}"
    candidate = f"{run_id}-{suffix}"
    if len(candidate) <= max_length:
        return candidate

    digest = hashlib.sha1(run_id.encode("utf-8")).hexdigest()[:8]
    reserved_length = len(f"-{digest}-{suffix}")
    prefix_length = max(1, max_length - reserved_length)
    prefix = run_id[:prefix_length].rstrip("-")
    return f"{prefix}-{digest}-{suffix}"


def cmd_preflight(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    benchmark_root = _benchmark_root()
    config = load_benchmark_yaml(benchmark_root / "benchmark.yaml")
    try:
        result = run_preflight(config, repo_root)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except RuntimeError as e:
        print(f"Preflight failed: {e}", file=sys.stderr)
        return 1


def cmd_run_single(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    benchmark_root = _benchmark_root()
    config = load_benchmark_yaml(benchmark_root / "benchmark.yaml")

    if not args.skip_preflight:
        try:
            run_preflight(config, repo_root)
        except RuntimeError as e:
            print(f"Preflight failed: {e}", file=sys.stderr)
            return 1

    condition = next((c for c in config.conditions if c.id == args.condition), None)
    if condition is None:
        print(f"Unknown condition: {args.condition}", file=sys.stderr)
        return 1

    task_dir = benchmark_root / "tasks" / args.task_id
    if not task_dir.exists():
        print(f"Task directory not found: {task_dir}", file=sys.stderr)
        return 1

    setup_script = task_dir / ("setup.py" if (task_dir / "setup.py").exists() else "setup.ps1")
    verifier_script = task_dir / ("verifier.py" if (task_dir / "verifier.py").exists() else "verifier.ps1")
    instruction_path = task_dir / "instruction.md"
    oracle_patch = task_dir / "oracle.patch"

    for p in [verifier_script, instruction_path]:
        if not p.exists():
            print(f"Required task file missing: {p}", file=sys.stderr)
            return 1

    run_id = args.run_id or _run_id_now()
    run_root = repo_root / config.runner.run_root
    layout = prepare_workspace(repo_root, run_root, run_id, args.task_id, condition, args.trial, config)

    workspace_root = Path(layout["workspace_root"])
    project_path = Path(layout["project_destination"])
    artifacts_path = Path(layout["artifacts_root"])
    skills_root = Path(layout["skills_root"]) if layout["skills_root"] else None

    # Copy instruction into workspace
    workspace_instruction = workspace_root / "instruction.md"
    workspace_instruction.write_text(instruction_path.read_text(encoding="utf-8"), encoding="utf-8")

    # Setup
    setup_stdout = artifacts_path / "setup.stdout.log"
    setup_stderr = artifacts_path / "setup.stderr.log"
    setup_result = {"exit_code": 0}
    if setup_script.exists():
        import subprocess

        env = {
            "WORKSPACE_ROOT": str(workspace_root),
            "PROJECT_PATH": str(project_path),
            "ARTIFACTS_PATH": str(artifacts_path),
        }
        if setup_script.suffix == ".py":
            cmd = [sys.executable, str(setup_script)]
        else:
            cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(setup_script)]
        result = subprocess.run(cmd, cwd=str(project_path), capture_output=True, text=True, env={**subprocess.os.environ, **env})
        setup_stdout.write_text(result.stdout, encoding="utf-8")
        setup_stderr.write_text(result.stderr, encoding="utf-8")
        setup_result["exit_code"] = result.returncode
        if result.returncode != 0:
            print(f"Setup failed: {setup_stderr}", file=sys.stderr)
            return 1

        # Commit setup baseline (allow empty in case setup makes no changes)
        subprocess.run(["git", "add", "-A"], cwd=str(project_path), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Task setup baseline", "--allow-empty"], cwd=str(project_path), check=True, capture_output=True)

    # Adapter
    adapter_name = args.adapter
    if adapter_name == "oracle":
        adapter = OracleAdapter()
    elif adapter_name == "manual":
        adapter = ManualAdapter()
    elif adapter_name == "noop":
        adapter = NoopAdapter()
    elif adapter_name == "kimi-code":
        adapter = KimiCodeAdapter()
    elif adapter_name == "codex":
        adapter = CodexAdapter()
    else:
        print(f"Unknown adapter: {adapter_name}", file=sys.stderr)
        return 1

    project_junction = Path(layout["project_junction"]) if layout.get("project_junction") else None
    adapter_result = adapter.run(
        workspace_root=workspace_root,
        instruction_path=workspace_instruction,
        skills_root=skills_root,
        artifacts_dir=artifacts_path,
        timeout_minutes=args.timeout_minutes,
        task_dir=task_dir,
        project_junction=project_junction,
    )

    # Git diff
    git_add_untracked(project_path)
    diff_path = artifacts_path / "git.diff"
    capture_git_diff(project_path, diff_path)
    filtered_diff_path = artifacts_path / "git.filtered.diff"
    capture_filtered_git_diff(project_path, filtered_diff_path)
    diff_metrics_result = diff_metrics(project_path)

    # Verifier (always with clean build for UE tasks)
    verifier_result = run_verifier(
        verifier_script=verifier_script,
        workspace_root=workspace_root,
        project_path=project_path,
        artifacts_path=artifacts_path,
        benchmark_root=benchmark_root,
        timeout_minutes=args.verifier_timeout,
    )
    automation_artifacts = collect_automation_artifacts(project_path, artifacts_path)
    skill_injection = describe_skill_injection(repo_root, workspace_root, config, condition, skills_root)

    junction_dir = layout.get("junction_dir")
    if junction_dir:
        try:
            from .junction import remove_junction
            remove_junction(Path(junction_dir))
        except Exception as exc:
            print(f"Warning: failed to remove junction {junction_dir}: {exc}", file=sys.stderr)

    overall_passed = (
        adapter_result.exit_code == 0
        and not adapter_result.timed_out
        and (verifier_result["verifier_result"] or {}).get("passed", False)
    )

    failure_class = None
    if adapter_result.exit_code != 0 or adapter_result.timed_out:
        failure_class = adapter_result.failure_class or "agent-crash"
    elif not (verifier_result["verifier_result"] or {}).get("passed", False):
        failure_class = (verifier_result["verifier_result"] or {}).get("failure_class", "verifier-fail")

    result = {
        "run_id": run_id,
        "task_id": args.task_id,
        "condition": args.condition,
        "trial": args.trial,
        **skill_injection,
        "agent": {
            "name": adapter_name,
            "exit_code": adapter_result.exit_code,
            "timed_out": adapter_result.timed_out,
            "duration_seconds": adapter_result.duration_seconds,
            "adapter_wall_seconds": adapter_result.adapter_wall_seconds,
            "failure_class": adapter_result.failure_class,
        },
        "verifier": {
            "exit_code": verifier_result["exit_code"],
            "passed": (verifier_result["verifier_result"] or {}).get("passed", False),
            "failure_class": (verifier_result["verifier_result"] or {}).get("failure_class"),
        },
        "overall_passed": overall_passed,
        "failure_class": failure_class,
        "metrics": {
            "wall_clock_seconds": round(
                adapter_result.adapter_wall_seconds
                + duration_seconds_or_zero((verifier_result["verifier_result"] or {}).get("build")),
                3,
            ),
            "build_duration_seconds": ((verifier_result["verifier_result"] or {}).get("build") or {}).get("duration_seconds"),
            "files_changed": diff_metrics_result["files_changed"],
            "lines_added": diff_metrics_result["lines_added"],
            "lines_deleted": diff_metrics_result["lines_deleted"],
            "automation_report_generated": bool(automation_artifacts),
        },
        "trajectory": {
            "command_invocations": "unknown",
            "skill_file_reads": "unknown",
        },
        "artifacts": {
            "workspace": str(project_path),
            "diff": str(diff_path),
            "verifier_result": str(artifacts_path / "verifier_result.json"),
            "automation": [str(path) for path in automation_artifacts],
        },
    }

    result_path = Path(layout["result_json"])
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if overall_passed else 1


def cmd_validate_task(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    benchmark_root = _benchmark_root()
    config = load_benchmark_yaml(benchmark_root / "benchmark.yaml")
    task_dir = benchmark_root / "tasks" / args.task_id
    task_toml = task_dir / "task.toml"
    if not task_toml.exists():
        print(f"Task not found: {args.task_id}", file=sys.stderr)
        return 1

    task = load_task_toml(task_toml)
    errors = validate_task_oracle_contract(task, task_dir)
    if errors:
        for error in errors:
            print(f"Task oracle validation failed: {error}", file=sys.stderr)
        return 1

    condition = next((c for c in config.conditions if c.id == "no-skills"), None)
    if condition is None:
        print("validate-task requires a no-skills condition", file=sys.stderr)
        return 1

    run_id = args.run_id or _run_id_now()
    for trial in range(1, args.repeat + 1):
        initial_args = argparse.Namespace(
            task_id=args.task_id,
            condition="no-skills",
            adapter="noop",
            trial=trial,
            run_id=validation_trial_run_id(run_id, "initial", trial),
            skip_preflight=True,
            timeout_minutes=args.timeout_minutes,
            verifier_timeout=args.verifier_timeout,
        )
        initial_rc = cmd_run_single(initial_args)
        initial_result_path = repo_root / config.runner.run_root / initial_args.run_id / "result.json"
        if not initial_result_path.exists():
            print(f"validate-task failed: setup or runner failed before verifier on trial {trial}", file=sys.stderr)
            return 1
        if initial_rc == 0:
            print(f"validate-task failed: setup state passed before oracle on trial {trial}", file=sys.stderr)
            return 1

        oracle_args = argparse.Namespace(
            task_id=args.task_id,
            condition="no-skills",
            adapter="oracle",
            trial=trial,
            run_id=validation_trial_run_id(run_id, "oracle", trial),
            skip_preflight=True,
            timeout_minutes=args.timeout_minutes,
            verifier_timeout=args.verifier_timeout,
        )
        oracle_rc = cmd_run_single(oracle_args)
        oracle_result_path = repo_root / config.runner.run_root / oracle_args.run_id / "result.json"
        if not oracle_result_path.exists():
            print(f"validate-task failed: oracle run did not produce result.json on trial {trial}", file=sys.stderr)
            return 1
        if oracle_rc != 0:
            print(f"validate-task failed: oracle state did not pass on trial {trial}", file=sys.stderr)
            return oracle_rc

    return 0


def cmd_run_matrix(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    benchmark_root = _benchmark_root()
    config = load_benchmark_yaml(benchmark_root / "benchmark.yaml")
    tasks_dir = benchmark_root / "tasks"
    tasks = discover_tasks(tasks_dir) if tasks_dir.exists() else []
    try:
        selected_tasks = select_matrix_tasks(tasks, args.task_id, args.task_filter)
        selected_conditions = select_matrix_conditions(config.conditions, args.condition)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    run_id = args.run_id or _run_id_now()
    trial_count = args.trials or config.runner.trials

    exit_codes = []
    sequence = 0
    for task in selected_tasks:
        for condition in selected_conditions:
            for trial in range(1, trial_count + 1):
                sequence += 1
                trial_run_id = matrix_trial_run_id(run_id, sequence)
                print(f"\n=== Running {trial_run_id} ===")
                sub_args = argparse.Namespace(
                    task_id=task.id,
                    condition=condition.id,
                    adapter=args.adapter,
                    trial=trial,
                    run_id=trial_run_id,
                    skip_preflight=True,  # preflight once at start is enough
                    timeout_minutes=30,
                    verifier_timeout=30,
                )
                rc = cmd_run_single(sub_args)
                exit_codes.append(rc)
                if rc != 0:
                    print(f"Trial failed: {trial_run_id}")

    return max(exit_codes) if exit_codes else 0


def cmd_report(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    benchmark_root = _benchmark_root()
    config = load_benchmark_yaml(benchmark_root / "benchmark.yaml")
    run_root = repo_root / config.runner.run_root
    output_dir = benchmark_root / "reports"
    try:
        result = make_report(run_root, args.run_id, output_dir)
        print(f"Report generated: {result['md_path']}")
        return 0
    except RuntimeError as e:
        print(f"Report failed: {e}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="UE5 SkillsBench Python Runner")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("preflight", help="Run environment checks")
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("run-single", help="Run a single trial")
    p.add_argument("--task-id", required=True)
    p.add_argument("--condition", required=True)
    p.add_argument("--adapter", choices=["oracle", "manual", "noop", "codex", "kimi-code"], required=True)
    p.add_argument("--trial", type=int, default=1)
    p.add_argument("--run-id", default=None)
    p.add_argument("--skip-preflight", action="store_true")
    p.add_argument("--timeout-minutes", type=int, default=45)
    p.add_argument("--verifier-timeout", type=int, default=30)
    p.set_defaults(func=cmd_run_single)

    p = sub.add_parser("validate-task", help="Validate setup failure and oracle success")
    p.add_argument("--task-id", required=True)
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument("--run-id", default=None)
    p.add_argument("--timeout-minutes", type=int, default=45)
    p.add_argument("--verifier-timeout", type=int, default=30)
    p.set_defaults(func=cmd_validate_task)

    p = sub.add_parser("run-matrix", help="Run full task/condition/trial matrix")
    p.add_argument("--adapter", choices=["oracle", "manual", "noop", "codex", "kimi-code"], required=True)
    p.add_argument("--run-id", default=None)
    p.add_argument("--task-id", action="append", default=[])
    p.add_argument("--task-filter", action="append", default=[])
    p.add_argument("--condition", action="append", default=[])
    p.add_argument("--trials", type=int, default=None)
    p.set_defaults(func=cmd_run_matrix)

    p = sub.add_parser("report", help="Generate report from previous run")
    p.add_argument("--run-id", required=True)
    p.set_defaults(func=cmd_report)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

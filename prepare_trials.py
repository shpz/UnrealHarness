"""Prepare all trial workspaces for Kimi Code runs."""
import json
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[0]
bench_root = repo_root / "benchmarks" / "ue5-skillsbench"
sys.path.insert(0, str(bench_root))

from runner.config import load_benchmark_yaml, ConditionConfig
from runner.workspace import prepare_workspace


def main():
    cfg = load_benchmark_yaml(bench_root / "benchmark.yaml")
    run_root = repo_root / cfg.runner.run_root

    conditions = ["no-skills", "ue-build-only"]
    trials = 5
    task_id = "tps-build-repair-transient-lock"

    layouts = {}
    for cond in conditions:
        condition = next(c for c in cfg.conditions if c.id == cond)
        for t in range(1, trials + 1):
            run_id = f"kimi-{task_id}-{cond}-t{t}"
            layout = prepare_workspace(repo_root, run_root, run_id, task_id, condition, t, cfg)
            layouts[(cond, t)] = layout
            print(f"Prepared {run_id}")

    # Save layouts
    layouts_file = repo_root / ".bench" / "layouts.json"
    layouts_file.write_text(json.dumps(layouts, indent=2), encoding="utf-8")
    print("All workspaces prepared. Saved to .bench/layouts.json")


if __name__ == "__main__":
    main()

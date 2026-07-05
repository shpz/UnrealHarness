# UE5 SkillsBench Runbook

This runbook is the operational entry point for `benchmarks/ue5-skillsbench`.

## Prerequisites

- Windows with PowerShell.
- Python available as `python`.
- Unreal Engine matching `sample/TPSample/TPSample.uproject` `EngineAssociation`.
- Coding agent CLI installed when running real-agent matrices, for example `codex` or `kimi`.

Run the environment check first:

```bash
python -m benchmarks.ue5-skillsbench.runner preflight
```

## Validate Task Oracles

Every formal task should prove both sides of its contract:

- setup state fails or lacks required artifacts;
- oracle state passes;
- repeated runs are deterministic.

Examples:

```bash
python -m benchmarks.ue5-skillsbench.runner validate-task --task-id tps-build-engine-resolve --repeat 3 --timeout-minutes 15 --verifier-timeout 15
python -m benchmarks.ue5-skillsbench.runner validate-task --task-id tps-autotest-run-scoped-report --repeat 3 --timeout-minutes 15 --verifier-timeout 15
python -m benchmarks.ue5-skillsbench.runner validate-task --task-id tps-autotest-add-input-math-tests --repeat 3 --timeout-minutes 15 --verifier-timeout 15
python -m benchmarks.ue5-skillsbench.runner validate-task --task-id tps-autotest-fix-failing-error-tests --repeat 3 --timeout-minutes 15 --verifier-timeout 15
python -m benchmarks.ue5-skillsbench.runner validate-task --task-id tps-build-fix-module-dependency --repeat 3 --timeout-minutes 15 --verifier-timeout 15
python -m benchmarks.ue5-skillsbench.runner validate-task --task-id tps-build-fix-enhanced-input-dependency --repeat 3 --timeout-minutes 15 --verifier-timeout 15
```

## Run A Single Trial

Use this for adapter debugging:

```bash
python -m benchmarks.ue5-skillsbench.runner run-single --task-id tps-build-fix-module-dependency --condition ue-autotest-with-build --adapter codex --trial 1 --run-id manual-smoke
```

Useful adapters:

- `noop`: leaves the setup state untouched.
- `oracle`: applies the task oracle.
- `codex`: runs the Codex CLI against the workspace.
- `kimi-code`: runs the Kimi Code CLI against the workspace.

## Run A Small Real-Agent Matrix

The MVP smoke matrix is:

```bash
python -m benchmarks.ue5-skillsbench.runner run-matrix --adapter codex --run-id phase-d-codex-smoke-v2 --task-id tps-build-fix-module-dependency --task-id tps-autotest-run-scoped-report --condition no-skills --condition ue-autotest-with-build --trials 2
```

This creates 8 trial directories:

```text
2 tasks x 2 conditions x 2 trials = 8 runs
```

Matrix trial directories use compact names such as `<run-id>-r001` to avoid Windows path length failures in UE `Intermediate` paths. Task, condition, and trial metadata are stored in each `result.json`.

## Generate Reports

Generate all report artifacts for a run id prefix:

```bash
python -m benchmarks.ue5-skillsbench.runner report --run-id phase-d-codex-smoke-v2
```

Outputs:

- `benchmarks/ue5-skillsbench/reports/<run-id>-results.json`
- `benchmarks/ue5-skillsbench/reports/<run-id>-summary.md`
- `benchmarks/ue5-skillsbench/reports/<run-id>-failures.md`

The summary includes pass rate, delta percentage points, normalized gain, mean and median durations, file and line change metrics, failure class distribution, and skill impact aggregation. The failures file lists each failed trial with failed verifier checks and artifact paths.

## Current Smoke Evidence

The first real Codex smoke matrix using compact run directories was:

```bash
python -m benchmarks.ue5-skillsbench.runner run-matrix --adapter codex --run-id phase-d-codex-smoke-v2 --task-id tps-build-fix-module-dependency --task-id tps-autotest-run-scoped-report --condition no-skills --condition ue-autotest-with-build --trials 2
python -m benchmarks.ue5-skillsbench.runner report --run-id phase-d-codex-smoke-v2
```

Observed result:

- `tps-build-fix-module-dependency`: 4/4 passed across both conditions.
- `tps-autotest-run-scoped-report`: 0/4 passed; failures are concentrated in Automation discovery/reporting completeness.
- Reports were written under `benchmarks/ue5-skillsbench/reports/phase-d-codex-smoke-v2-*`.

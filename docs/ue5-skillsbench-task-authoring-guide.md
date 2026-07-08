# UE5 SkillsBench Task Authoring Guide

This guide describes the task contract used by `benchmarks/ue5-skillsbench/tasks/<task-id>/`.

## Required Files

Each task directory should contain:

```text
task.toml
instruction.md
setup.py
verifier.py
oracle.py or oracle.patch
```

Optional files:

```text
fixtures/
README.md
```

`instruction.md` is the only task-specific instruction shown to an agent. Do not mention verifier internals or tell the agent which skill condition is active.

## `task.toml`

Formal tasks must declare an oracle:

```toml
id = "tps-build-fix-module-dependency"
project = "TPSample"
timeout_minutes = 45
benchmark_role = "formal"
primary_skills = ["ue-build"]

[oracle]
type = "action"
path = "oracle.py"
repeat = 3

[verifier]
type = "python"
path = "verifier.py"
timeout_minutes = 45

[artifacts]
required = ["verifier_result.json", "build.log"]
```

Use `benchmark_role = "smoke"` and `[oracle].type = "none"` only for non-formal smoke tasks.

## Setup Contract

`setup.py` runs inside the copied trial project workspace. It must not modify `sample/TPSample`.

Setup should create a meaningful failing state:

- build repair tasks should fail to build or be missing required build artifacts;
- Automation authoring tasks should be buildable but missing required test modules or scopes;
- Automation repair tasks should include existing failing tests;
- reporting tasks should be missing required runtime artifacts until the agent runs the correct scope.

After setup, the runner commits a git baseline in the trial workspace. Verifiers and reports use diffs against that setup baseline.

## Oracle Contract

Formal task oracles prove the task is solvable and the verifier is fair.

Use `oracle.py` for action-oriented tasks, for example running Automation scopes or applying structured source edits. Use `oracle.patch` when a static patch is simpler.

Oracle validation must pass:

```bash
python -m benchmarks.ue5-skillsbench.runner validate-task --task-id <task-id> --repeat 3
```

The command checks:

- setup plus noop fails;
- setup plus oracle passes;
- the sequence repeats successfully.

## Verifier Contract

`verifier.py` receives:

- `PROJECT_PATH`
- `ARTIFACTS_PATH`
- `BENCHMARK_ROOT`

It must write `ARTIFACTS_PATH/verifier_result.json` using the shared schema:

```json
{
  "passed": false,
  "failure_class": "build",
  "checks": [
    {"name": "ubt_build", "passed": false, "details": "compiler output summary"}
  ]
}
```

Use `benchmarks/ue5-skillsbench/runner/verifier_result.py` to build and validate result objects.

For UE Automation tasks, use `benchmarks/ue5-skillsbench/runner/automation_report.py` to parse native reports, `autotest_results.json`, or editor logs. Do not parse skill directories or rely on agent claims.

Automation verifiers should not trust workspace report files alone: they can be fabricated. Use `benchmarks/ue5-skillsbench/runner/authoritative_rerun.py` to rerun the requested scope during verification. The runner enables reruns for real trials via `SKILLSBENCH_RERUN_AUTOMATION=1`; unit tests and engine-less environments set it to `0` and fall back to artifact parsing. For execution-only tasks (no source changes allowed), corroborate structured reports against editor-log evidence via `parse_editor_log_evidence`.

## Failure Classes

Use stable failure classes so reports can aggregate failures across tasks:

- `setup`
- `build`
- `registration`
- `automation-discovery`
- `test`
- `reporting`
- `scope`
- `cheating`
- `agent-crash`
- `timeout`
- `verifier-error`

Prefer the most specific class that explains the first blocking failed check.

## Artifacts

The runner writes trial artifacts under:

```text
.bench/runs/<trial-run-id>/artifacts/
```

Common artifacts:

```text
agent.prompt.md
agent.stdout.log
agent.stderr.log
setup.stdout.log
setup.stderr.log
verifier.stdout.log
verifier.stderr.log
git.diff
git.filtered.diff
result.json
verifier_result.json
build.log
automation/
```

Automation artifacts copied by the runner may include:

```text
automation/index.json
automation/autotest_results.json
automation/report.md
automation/editor.log
```

## Anti-Cheating Checks

Repair task verifiers should reject shortcuts that satisfy only superficial artifacts:

- deleting required tests;
- renaming scopes away from the requested scope;
- weakening assertions;
- adding early `return true` paths;
- modifying generated reports by hand instead of running the workflow;
- changing source to avoid the intended dependency or behavior.

Static source checks should be paired with runtime artifact checks. A passing report alone is not enough for repair tasks.

# Design: Fix UE Autotest Benchmark Failures

## Status

Approved.

## Goal

Eliminate the root causes observed in the latest round of `ue-autotest` benchmark runs and improve the pass rate for both `no-skills` and `ue-autotest-with-build` conditions.

## Background

A full matrix run of the three `ue-autotest` tasks (`tps-autotest-fix-failing-error-tests`, `tps-autotest-add-input-math-tests`, `tps-autotest-run-scoped-report`) under both `no-skills` and `ue-autotest-with-build` conditions produced 6 failures. Root-cause analysis showed a mix of framework/task-design bugs and agent-behavior issues:

| Task | Condition | Failure Class | Root Cause |
|---|---|---|---|
| fix-failing-error-tests | no-skills | `cheating` | Verifier anti-cheat regex is too narrow; it does not recognize a legitimate `TSet`-based fix in the production helper. |
| fix-failing-error-tests | ue-autotest-with-build | `automation-discovery` | `autotest.py` writes a synthetic failed test record when no real UE report is parsed; the agent also returned before the test run completed. |
| add-input-math-tests | no-skills | `registration` | Agent created a `TPSampleEditor` module instead of the expected `TPSampleTest` Editor module. |
| add-input-math-tests | ue-autotest-with-build | `automation-discovery` | Agent started `autotest.py` in the background and exited before it finished. |
| run-scoped-report | no-skills | `reporting` | Native Automation report was generated and all 6 tests passed, but no markdown summary report was produced. |
| run-scoped-report | ue-autotest-with-build | `automation-discovery` | Agent started `autotest.py` in the background and exited before it finished. |

## Scope

This design covers changes to:

1. `skills/ue-autotest/scripts/autotest.py`
2. `benchmarks/ue5-skillsbench/runner/automation_report.py`
3. `benchmarks/ue5-skillsbench/tasks/tps-autotest-fix-failing-error-tests/verifier.py`
4. `benchmarks/ue5-skillsbench/tasks/tps-autotest-add-input-math-tests/instruction.md`
5. `benchmarks/ue5-skillsbench/tasks/tps-autotest-run-scoped-report/instruction.md`
6. `benchmarks/ue5-skillsbench/runner/adapter.py` (`KimiCodeAdapter` prompt and post-run checks)

## Design

### 1. Remove synthetic placeholder tests from `autotest.py` output

**Current behavior:** When `parse_report_results` returns zero tests, `invoke_test_run` injects a placeholder test:

```python
{
    "name": f"{mod} (NO TESTS PARSED)",
    "passed": False,
    ...
}
```

If the editor times out, it also injects `f"{mod} (TIMEOUT)"` with `passed: False`.

**Problem:** The benchmark verifier treats these as real executed tests, causing false `test` failures.

**New behavior:**
- Do not inject `(NO TESTS PASSED)` placeholder tests.
- Do not inject `(TIMEOUT)` placeholder tests into the `tests` array. Instead, surface timeout status in module metadata (`timedOut: true`) without fabricating a test result.
- If no real tests are parsed, the module's `tests` array remains empty. The overall JSON file is still written so that humans can inspect it, but the verifier's `can_confirm_results` will be `False`, leading it to report `automation-discovery` instead of a fake `test` failure.

### 2. Filter synthetic placeholder names in `automation_report.py`

**Defense in depth:** Even if other scripts or future regressions inject placeholder records, the shared report parser should ignore them.

**New behavior:** In `_parse_autotest_results`, skip any test whose name ends with `(NO TESTS PARSED)` or `(TIMEOUT)` or other known synthetic suffixes. This prevents the verifier from counting them as executed tests.

### 3. Tighten `production_helper_touched` anti-cheat check

**Current behavior:** The verifier requires the production helper source to contain either `Event.Code == Code` or `FindByPredicate`. An agent that deduplicates errors using a `TSet<FString>` in `Flush` is marked as `cheating`.

**New behavior:** Pass the check if the production helper `Source/TPSample/Private/TPSampleErrorAccumulator.cpp` was meaningfully modified. "Meaningful" means:

- The file differs from the setup baseline (verified with `git diff HEAD -- <file>`).
- The diff is not only whitespace or comment-only changes.
- The diff contains evidence of deduplication by error code, such as any of:
  - `Event.Code == Code` comparison
  - `ContainsByPredicate` / `FindByPredicate` on `PendingErrors`
  - `TSet`, `TMap`, `TArray::Contains`, or similar set/map lookup on `Code`
  - `PendingErrors.RemoveAll` / `RemoveAllSwap` with a code-based predicate

This keeps the anti-cheat semantic (the helper must actually implement deduplication by code) while allowing multiple valid implementation patterns.

### 4. Clarify task instructions

#### `tps-autotest-add-input-math-tests/instruction.md`

Add explicit language:

> Create a new Editor test module named exactly `TPSampleTest` under `Source/TPSampleTest`. Do not place the tests in `TPSampleEditor` or any other module name.

#### `tps-autotest-run-scoped-report/instruction.md`

Add explicit language:

> After running the tests, write a markdown summary report under `Saved/Automation/Reports/` that includes the selected scopes, total/passed/failed counts, and failure details (or "No failures").

### 5. Enforce workspace contract in `KimiCodeAdapter`

#### 5.1 Prompt-level guard

Append a short contract to the prompt constructed in `KimiCodeAdapter.run()`:

```markdown
## Workspace Contract

- All compilation, test execution, and report generation must happen inside the current project directory.
- Do not create additional git worktrees or copy the project to an external path (such as `C:\TPSample` or `C:\.kh\...`) to run Unreal Engine commands.
- When invoking long-running scripts such as `autotest.py`, wait for the process to finish. Do not run them in the background.
```

#### 5.2 Adapter-level post-run enforcement

After the `kimi` subprocess returns, before returning `AdapterResult`, perform two checks:

1. **Lingering process wait:**
   - Look for any running `autotest.py`, `python.exe` whose command line contains the project path and `autotest.py`, or `UnrealEditor-Cmd.exe` whose command line contains the project path.
   - Wait up to `editor_timeout_seconds` (default 600) for them to finish.
   - If any are still running, terminate them and return `failure_class="agent-crash"` (or a new `failure_class="lingering-process"`).

2. **Worktree detection:**
   - Run `git rev-parse --git-dir` in `project_path`.
   - If the result points outside `project_path` or is a `.git` worktree file (not a directory), it indicates the agent switched to an external worktree.
   - Treat this as a failure and return `failure_class="agent-crash"`.

These checks make the expected improvement for `ue-autotest-with-build` runs real instead of relying solely on prompt compliance.

## Verification

After implementing these changes, rerun:

```bash
python run_autotest_benchmarks.py
```

Expected improvements:

- `fix-failing-error-tests` / no-skills passes `production_helper_touched` and is no longer classified as `cheating`.
- `add-input-math-tests` / no-skills passes registration checks because the agent creates `TPSampleTest`.
- `run-scoped-report` / no-skills passes `markdown_report` because the instruction now requires it.
- All three `ue-autotest-with-build` runs either complete within the adapter timeout or are flagged as `agent-crash`/`lingering-process` if they leave background processes.

### Unit / Behavioral Tests to Add

1. `autotest.py`: Assert that when no tests are parsed, `autotest_results.json` contains an empty `tests` array and `timedOut: false`, not a `(NO TESTS PASSED)` entry.
2. `autotest.py`: Assert that on timeout, `timedOut: true` is set but no `(TIMEOUT)` test entry is written.
3. `automation_report.py`: Assert that `_parse_autotest_results` ignores records whose names end with `(NO TESTS PARSED)` or `(TIMEOUT)`.
4. `tps-autotest-fix-failing-error-tests/verifier.py`: Assert that a helper modified with `TSet<FString>` passes `production_helper_touched`, while a helper with only whitespace changes fails.
5. `adapter.py`: Assert that the generated `agent.prompt.md` contains the workspace contract.
6. (Optional) `adapter.py`: Add a mock lingering-process test if feasible without running real UE.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Adapter-level process detection may be OS-specific or flaky. | Use process name + command-line substring matching on Windows; keep timeout generous; only fail if processes are still running after the wait. |
| Worktree detection could false-positive on legitimate submodule setups. | The benchmark workspaces are simple git repos; `rev-parse --git-dir` returning a file outside the project is a strong worktree signal. |
| Semantic anti-cheat patterns may still miss valid deduplication approaches. | The pattern set is intentionally broad (`TSet`, `TMap`, `Contains`, `RemoveAll`, predicate lambdas); if new valid approaches appear, extend the list. |
| Changing `autotest.py` behavior could affect other consumers. | The placeholder records are internal to this skill; module metadata still carries `timedOut` and `exitCode`, so callers can detect issues without fake test records. |

## Out of Scope

- Major refactoring of the `ue-autotest` skill's testing-patterns or report generation is not included.
- Cross-adapter enforcement (Codex, etc.) is not included unless requested.

## Next Step

After the updated design is approved, invoke the `writing-plans` skill to produce the implementation plan.

# Fix UE Autotest Benchmark Failures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the root causes of the 6 observed `ue-autotest` benchmark failures by fixing `autotest.py` placeholder records, tightening verifier anti-cheat, clarifying instructions, and enforcing workspace contracts in the KimiCode adapter.

**Architecture:** Make four small, focused changes to framework/task code (autotest runner, report parser, verifier, instructions) plus two changes to the KimiCode adapter (prompt guard and post-run process/worktree enforcement). Each change is independently testable.

**Tech Stack:** Python 3.14, Unreal Engine 5.7, pytest, unittest, Windows process APIs (`subprocess`, `tasklist`, `psutil` if available).

## Global Constraints

- All changes must keep the benchmark runner passing its existing test suite.
- Do not change the public interface of `AdapterResult` unless necessary.
- Do not introduce new third-party dependencies unless fallback behavior is provided.
- All file paths use POSIX forward slashes in documentation; Windows paths are shown with backslashes only when matching actual tool output.
- Tests must be runnable with `python -m pytest tests/benchmark_runner/` from the repository root.

---

## File Structure

| File | Responsibility |
|---|---|
| `skills/ue-autotest/scripts/autotest.py` | UE5 automation test runner. Will stop injecting synthetic `(NO TESTS PASSED)` and `(TIMEOUT)` test records. |
| `benchmarks/ue5-skillsbench/runner/automation_report.py` | Shared report parser. Will filter synthetic placeholder names from `autotest_results.json`. |
| `benchmarks/ue5-skillsbench/tasks/tps-autotest-fix-failing-error-tests/verifier.py` | Task verifier. Will use semantic anti-cheat patterns plus git-diff validation. |
| `benchmarks/ue5-skillsbench/tasks/tps-autotest-add-input-math-tests/instruction.md` | Task instruction. Will explicitly require `TPSampleTest` module name. |
| `benchmarks/ue5-skillsbench/tasks/tps-autotest-run-scoped-report/instruction.md` | Task instruction. Will explicitly require a markdown report. |
| `benchmarks/ue5-skillsbench/runner/adapter.py` | Adapter base + KimiCode adapter. Will append workspace contract to prompt and add post-run process/worktree checks. |
| `tests/benchmark_runner/test_autotest_skill.py` | New test file for `autotest.py` placeholder behavior. |
| `tests/benchmark_runner/test_automation_report.py` | Existing test file; add synthetic-name filtering test. |
| `tests/benchmark_runner/test_fix_failing_error_task_verifier.py` | Existing test file; add TSet/whitespace-only diff tests. |
| `tests/benchmark_runner/test_kimi_code_adapter.py` | New test file for adapter prompt and post-run checks. |

---

### Task 1: Remove synthetic placeholder tests from `autotest.py`

**Files:**
- Modify: `skills/ue-autotest/scripts/autotest.py`
- Create: `tests/benchmark_runner/test_autotest_skill.py`

**Interfaces:**
- Consumes: `run_result` dict from `run_tests`, `parse_test_results` output.
- Produces: `all_results` dict with empty `tests` arrays when no real tests are parsed; module metadata `timedOut: true` on timeout without synthetic test records.

- [ ] **Step 1: Refactor `invoke_test_run` to extract `_build_module_results`**

In `skills/ue-autotest/scripts/autotest.py`, extract the module result construction from `invoke_test_run` into a new helper `_build_module_results`:

```python
def _build_module_results(
    buckets: dict[str, list[dict[str, Any]]],
    mod: str,
    module_prefixes: dict[str, str],
    filters: list[str],
    run_result: dict[str, Any],
) -> dict[str, Any]:
    results = {
        "tests": list(buckets.get(mod, [])),
        "summary": {"total": 0, "passed": 0, "failed": 0, "duration_ms": 0},
    }
    _recompute_summary(results)

    return {
        "name": mod,
        "filter": module_prefixes.get(mod, "+".join(filters)),
        "exitCode": run_result["exitCode"],
        "timedOut": run_result["timedOut"],
        "logFile": str(run_result["logFile"]),
        "rawReportDir": str(run_result["reportDir"]),
        "results": results,
    }
```

Then replace the inline loop body in `invoke_test_run` with:

```python
for mod in bucket_names:
    module_result = _build_module_results(buckets, mod, module_prefixes, filters, run_result)
    all_results["modules"].append(module_result)

    module_tests = module_result["results"]["tests"]
    all_results["overall"]["total"] += len(module_tests)
    all_results["overall"]["passed"] += sum(1 for t in module_tests if t.get("passed"))
    all_results["overall"]["failed"] += sum(1 for t in module_tests if not t.get("passed"))
```

- [ ] **Step 2: Write the failing test**

Create `tests/benchmark_runner/test_autotest_skill.py`:

```python
from __future__ import annotations

import importlib
from pathlib import Path
import unittest


autotest = importlib.import_module("skills.ue-autotest.scripts.autotest")


class AutotestPlaceholderTests(unittest.TestCase):
    def test_build_module_results_does_not_inject_placeholder(self) -> None:
        run_result = {
            "exitCode": 0,
            "timedOut": False,
            "logFile": Path("C:/tmp/log.log"),
            "reportDir": Path("C:/tmp/report"),
        }
        module_result = autotest._build_module_results(
            buckets={"TPSampleTest": []},
            mod="TPSampleTest",
            module_prefixes={"TPSampleTest": "TPSample.Error"},
            filters=["TPSample.Error"],
            run_result=run_result,
        )

        self.assertEqual(module_result["name"], "TPSampleTest")
        self.assertEqual(module_result["results"]["tests"], [])
        self.assertFalse(module_result["timedOut"])
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
python -m pytest tests/benchmark_runner/test_autotest_skill.py -v
```

Expected: FAIL because `_build_module_results` (extracted from `invoke_test_run`) currently injects `(NO TESTS PASSED)`.

- [ ] **Step 4: Modify `_build_module_results` to skip placeholder injection**

In `skills/ue-autotest/scripts/autotest.py`, ensure `_build_module_results` does **not** append `(NO TESTS PASSED)` or `(TIMEOUT)` placeholder tests. The `timedOut` flag is already stored in `module_result`, so the placeholder test record is redundant.

Confirm the helper body matches:

```python
def _build_module_results(
    buckets: dict[str, list[dict[str, Any]]],
    mod: str,
    module_prefixes: dict[str, str],
    filters: list[str],
    run_result: dict[str, Any],
) -> dict[str, Any]:
    results = {
        "tests": list(buckets.get(mod, [])),
        "summary": {"total": 0, "passed": 0, "failed": 0, "duration_ms": 0},
    }
    _recompute_summary(results)

    return {
        "name": mod,
        "filter": module_prefixes.get(mod, "+".join(filters)),
        "exitCode": run_result["exitCode"],
        "timedOut": run_result["timedOut"],
        "logFile": str(run_result["logFile"]),
        "rawReportDir": str(run_result["reportDir"]),
        "results": results,
    }
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
python -m pytest tests/benchmark_runner/test_autotest_skill.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add skills/ue-autotest/scripts/autotest.py tests/benchmark_runner/test_autotest_skill.py
git commit -m "fix(autotest): stop injecting synthetic NO TESTS PASSED/TIMEOUT records"
```

---

### Task 2: Filter synthetic placeholder names in `automation_report.py`

**Files:**
- Modify: `benchmarks/ue5-skillsbench/runner/automation_report.py`
- Modify: `tests/benchmark_runner/test_automation_report.py`

**Interfaces:**
- Consumes: `autotest_results.json` content.
- Produces: `AutomationReportResult` with synthetic placeholder tests excluded.

- [ ] **Step 1: Write the failing test**

Append to `tests/benchmark_runner/test_automation_report.py`:

```python
    def test_autotest_results_ignore_synthetic_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            automation_dir = project / "Saved" / "Automation"
            automation_dir.mkdir(parents=True)
            (automation_dir / "autotest_results.json").write_text(
                json.dumps(
                    {
                        "modules": [
                            {
                                "name": "TPSampleTest",
                                "results": {
                                    "tests": [
                                        {"name": "TPSampleTest (NO TESTS PARSED)", "passed": False},
                                        {"name": "TPSampleTest (TIMEOUT)", "passed": False},
                                        {"name": "TPSample.Input.Math.Normalize", "passed": True},
                                    ]
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = automation_report.parse_automation_report(project)

        self.assertEqual(result.parser, "autotest-results-json")
        self.assertEqual(result.executed_tests, 1)
        self.assertEqual(result.passed_tests, 1)
        self.assertEqual([test.name for test in result.tests], ["TPSample.Input.Math.Normalize"])
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/benchmark_runner/test_automation_report.py::AutomationReportTests::test_autotest_results_ignore_synthetic_placeholders -v
```

Expected: FAIL because placeholders are currently counted.

- [ ] **Step 3: Implement filtering in `automation_report.py`**

In `benchmarks/ue5-skillsbench/runner/automation_report.py`, add a helper and use it in `_parse_autotest_results`:

```python
_SYNTHETIC_SUFFIXES = ("(NO TESTS PARSED)", "(TIMEOUT)")


def _is_synthetic_test_name(name: str) -> bool:
    return any(name.strip().endswith(suffix) for suffix in _SYNTHETIC_SUFFIXES)
```

In `_parse_autotest_results`, skip synthetic names:

```python
for module in raw.get("modules") or []:
    results = module.get("results") or {}
    for test in results.get("tests") or []:
        name = str(test.get("name") or "").strip()
        if not name or _is_synthetic_test_name(name):
            continue
        tests.append(
            AutomationTestResult(
                name=name,
                passed=bool(test.get("passed")),
                error=str(test.get("error")) if test.get("error") else None,
            )
        )
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/benchmark_runner/test_automation_report.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add benchmarks/ue5-skillsbench/runner/automation_report.py tests/benchmark_runner/test_automation_report.py
git commit -m "fix(automation_report): ignore synthetic placeholder test names"
```

---

### Task 3: Tighten `production_helper_touched` anti-cheat check

**Files:**
- Modify: `benchmarks/ue5-skillsbench/tasks/tps-autotest-fix-failing-error-tests/verifier.py`
- Modify: `tests/benchmark_runner/test_fix_failing_error_task_verifier.py`

**Interfaces:**
- Consumes: `project_path`, setup-baseline git state.
- Produces: `production_helper_touched` check result that accepts multiple deduplication patterns and rejects whitespace-only changes.

- [ ] **Step 1: Write the failing tests**

Append to `tests/benchmark_runner/test_fix_failing_error_task_verifier.py`:

```python
    def test_verifier_accepts_tset_dedup_in_flush(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            _write_project_shell(
                project,
                helper_code='''
void FTPSampleErrorAccumulator::ReportError(const FString& Code, const FString& Message)
{
    PendingErrors.Add({Code, Message});
}

int32 FTPSampleErrorAccumulator::Flush(TFunctionRef<void(const FString& Code, const FString& Message)> OnError)
{
    int32 BroadcastCount = 0;
    TSet<FString> BroadcastCodes;
    for (const FTPSampleErrorEvent& Event : PendingErrors)
    {
        if (!BroadcastCodes.Contains(Event.Code))
        {
            OnError(Event.Code, Event.Message);
            BroadcastCodes.Add(Event.Code);
            ++BroadcastCount;
        }
    }
    PendingErrors.Reset();
    return BroadcastCount;
}
''',
            )
            _write_test_module(project, strong_assertion=True)
            _write_report(
                project,
                [
                    "TPSample.Error.Accumulator.RecordsErrors",
                    "TPSample.Error.Accumulator.FlushClearsQueue",
                    "TPSample.Error.Accumulator.DedupesBroadcast",
                ],
            )
            artifacts = root / "artifacts"
            artifacts.mkdir()

            result = _run_verifier(project, artifacts)

            self.assertEqual(result.returncode, 0, result.stderr)
            verifier_result = json.loads((artifacts / "verifier_result.json").read_text(encoding="utf-8"))
            self.assertTrue(verifier_result["passed"])

    def test_verifier_rejects_whitespace_only_helper_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            _write_project_shell(project)
            # Modify helper with only whitespace/comment changes
            helper_path = project / "Source" / "TPSample" / "Private" / "TPSampleErrorAccumulator.cpp"
            original = helper_path.read_text(encoding="utf-8")
            helper_path.write_text(original + "\n// no-op comment\n", encoding="utf-8")
            _write_test_module(project, strong_assertion=True)
            _write_report(
                project,
                [
                    "TPSample.Error.Accumulator.RecordsErrors",
                    "TPSample.Error.Accumulator.FlushClearsQueue",
                    "TPSample.Error.Accumulator.DedupesBroadcast",
                ],
            )
            artifacts = root / "artifacts"
            artifacts.mkdir()

            result = _run_verifier(project, artifacts)

            self.assertNotEqual(result.returncode, 0)
            verifier_result = json.loads((artifacts / "verifier_result.json").read_text(encoding="utf-8"))
            self.assertEqual(verifier_result["failure_class"], "cheating")
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/benchmark_runner/test_fix_failing_error_task_verifier.py -v
```

Expected: The two new tests FAIL (TSet rejected, whitespace-only accepted).

- [ ] **Step 3: Implement semantic anti-cheat in the verifier**

In `benchmarks/ue5-skillsbench/tasks/tps-autotest-fix-failing-error-tests/verifier.py`, replace `_anti_cheat_checks` and add helpers:

```python
_DEDUPE_PATTERNS = [
    re.compile(r"\b\w+\.Code\s*==\s*Code\b"),
    re.compile(r"FindByPredicate|ContainsByPredicate"),
    re.compile(r"\bTSet\s*<"),
    re.compile(r"\bTMap\s*<"),
    re.compile(r"\bTArray\s*<[^>]*>\s*::\s*Contains\b"),
    re.compile(r"\bRemoveAll\b|\bRemoveAllSwap\b"),
]


def _helper_has_meaningful_diff(project_path: Path) -> bool:
    helper_source = project_path / "Source" / "TPSample" / "Private" / "TPSampleErrorAccumulator.cpp"
    if not helper_source.exists():
        return False
    result = subprocess.run(
        ["git", "diff", "HEAD", "--", str(helper_source)],
        cwd=project_path,
        capture_output=True,
        text=True,
    )
    diff = result.stdout.strip()
    if not diff:
        return False
    # Reject diffs that are only whitespace or comment changes
    for line in diff.splitlines():
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            stripped = line[1:].strip()
            if stripped and not stripped.startswith("//") and not stripped.startswith("/*") and not stripped.endswith("*/"):
                return True
    return False


def _helper_implements_code_dedup(helper_text: str) -> bool:
    return any(pattern.search(helper_text) for pattern in _DEDUPE_PATTERNS)
```

Then update the `production_helper_touched` check:

```python
{"name": "production_helper_touched", "passed": _helper_has_meaningful_diff(project_path) and _helper_implements_code_dedup(helper_text)},
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/benchmark_runner/test_fix_failing_error_task_verifier.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add benchmarks/ue5-skillsbench/tasks/tps-autotest-fix-failing-error-tests/verifier.py tests/benchmark_runner/test_fix_failing_error_task_verifier.py
git commit -m "fix(verifier): accept semantic deduplication patterns in production helper"
```

---

### Task 4: Clarify task instructions

**Files:**
- Modify: `benchmarks/ue5-skillsbench/tasks/tps-autotest-add-input-math-tests/instruction.md`
- Modify: `benchmarks/ue5-skillsbench/tasks/tps-autotest-run-scoped-report/instruction.md`

**Interfaces:**
- Consumes: N/A.
- Produces: Updated task instructions read by the agent adapter.

- [ ] **Step 1: Update `add-input-math-tests` instruction**

Edit `benchmarks/ue5-skillsbench/tasks/tps-autotest-add-input-math-tests/instruction.md` to add module name constraint:

```markdown
# Task

Add UE Automation tests for TPSample input math behavior.

The project now has a small input math helper in the main TPSample module. Create the required Editor test module and add at least three headless Automation tests under `TPSample.Input.Math.*`.

Create a new Editor test module named exactly `TPSampleTest` under `Source/TPSampleTest`. Do not place the tests in `TPSampleEditor` or any other module name.

Cover these cases:

- Normalizing move input outside the dead zone.
- Treating tiny move input as inside the dead zone.
- Quantizing look input to a stable step size.

Run the new test scope and leave the Automation results in the project so the run can be reviewed.
```

- [ ] **Step 2: Update `run-scoped-report` instruction**

Edit `benchmarks/ue5-skillsbench/tasks/tps-autotest-run-scoped-report/instruction.md` to add markdown report requirement:

```markdown
# Run Scoped Automation Report

The project already contains multiple UE Automation test scopes.

Run only the input and error handling related tests. Do not run performance tests. Produce a pass/fail summary and include the report file path.

After running the tests, write a markdown summary report under `Saved/Automation/Reports/` that includes the selected scopes, total/passed/failed counts, and failure details (or "No failures").
```

- [ ] **Step 3: Verify with grep**

```bash
grep -n "TPSampleTest" benchmarks/ue5-skillsbench/tasks/tps-autotest-add-input-math-tests/instruction.md
grep -n "markdown" benchmarks/ue5-skillsbench/tasks/tps-autotest-run-scoped-report/instruction.md
```

Expected: Both commands return matching lines.

- [ ] **Step 4: Commit**

```bash
git add benchmarks/ue5-skillsbench/tasks/tps-autotest-add-input-math-tests/instruction.md benchmarks/ue5-skillsbench/tasks/tps-autotest-run-scoped-report/instruction.md
git commit -m "docs(tasks): clarify test module name and markdown report requirements"
```

---

### Task 5: Add workspace contract to KimiCodeAdapter prompt

**Files:**
- Modify: `benchmarks/ue5-skillsbench/runner/adapter.py`
- Create: `tests/benchmark_runner/test_kimi_code_adapter.py`

**Interfaces:**
- Consumes: Existing prompt construction in `KimiCodeAdapter.run`.
- Produces: `agent.prompt.md` containing workspace contract; `AdapterResult` unchanged.

- [ ] **Step 1: Write the failing test**

Create `tests/benchmark_runner/test_kimi_code_adapter.py`:

```python
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from benchmarks.ue5_skillsbench.runner.adapter import KimiCodeAdapter


class KimiCodeAdapterPromptTests(unittest.TestCase):
    def test_prompt_contains_workspace_contract(self) -> None:
        adapter = KimiCodeAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp)
            workspace_root.mkdir()
            project_path = workspace_root / "TPSample"
            project_path.mkdir()
            artifacts_dir = workspace_root / "artifacts"
            artifacts_dir.mkdir()
            instruction_path = workspace_root / "instruction.md"
            instruction_path.write_text("Run tests.", encoding="utf-8")

            # _find_kimi requires the executable to exist; mock it
            adapter._find_kimi = lambda: Path("/fake/kimi.exe")  # type: ignore[method-assign]

            adapter.run(
                workspace_root=workspace_root,
                instruction_path=instruction_path,
                skills_root=None,
                artifacts_dir=artifacts_dir,
                timeout_minutes=1,
            )

            prompt = (artifacts_dir / "agent.prompt.md").read_text(encoding="utf-8")
            self.assertIn("Workspace Contract", prompt)
            self.assertIn("current project directory", prompt)
            self.assertIn("Do not create additional git worktrees", prompt)
            self.assertIn("wait for the process to finish", prompt)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/benchmark_runner/test_kimi_code_adapter.py -v
```

Expected: FAIL because the workspace contract is not yet in the prompt.

- [ ] **Step 3: Append workspace contract to prompt**

In `benchmarks/ue5-skillsbench/runner/adapter.py`, in `KimiCodeAdapter.run`, after constructing `prompt` and before writing `prompt_path`, append:

```python
        prompt_parts.append("\n\n## Workspace Contract\n\n")
        prompt_parts.append(
            "- All compilation, test execution, and report generation must happen inside the current project directory.\n"
            "- Do not create additional git worktrees or copy the project to an external path to run Unreal Engine commands.\n"
            "- When invoking long-running scripts such as autotest.py, wait for the process to finish. Do not run them in the background.\n"
        )
        prompt = "\n".join(prompt_parts)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/benchmark_runner/test_kimi_code_adapter.py::KimiCodeAdapterPromptTests -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add benchmarks/ue5-skillsbench/runner/adapter.py tests/benchmark_runner/test_kimi_code_adapter.py
git commit -m "feat(adapter): add workspace contract to KimiCodeAdapter prompt"
```

---

### Task 6: Add adapter-level post-run enforcement

**Files:**
- Modify: `benchmarks/ue5-skillsbench/runner/adapter.py`
- Modify: `tests/benchmark_runner/test_kimi_code_adapter.py`

**Interfaces:**
- Consumes: `project_path` after Kimi subprocess exits.
- Produces: `AdapterResult` with `failure_class="agent-crash"` if lingering processes or external worktrees are detected.

- [ ] **Step 1: Write the failing tests**

Append to `tests/benchmark_runner/test_kimi_code_adapter.py`:

```python
import subprocess


class KimiCodeAdapterPostRunTests(unittest.TestCase):
    def test_detects_external_git_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp)
            workspace_root.mkdir()
            project_path = workspace_root / "TPSample"
            project_path.mkdir()
            artifacts_dir = workspace_root / "artifacts"
            artifacts_dir.mkdir()
            instruction_path = workspace_root / "instruction.md"
            instruction_path.write_text("Run tests.", encoding="utf-8")

            # Initialize a git repo with an external worktree pointer
            subprocess.run(["git", "init"], cwd=project_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "test"], cwd=project_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=project_path, check=True, capture_output=True)
            git_file = project_path / ".git"
            git_file.write_text("gitdir: /fake/external/.git\n", encoding="utf-8")

            adapter = KimiCodeAdapter()
            adapter._find_kimi = lambda: Path("/fake/kimi.exe")  # type: ignore[method-assign]

            result = adapter.run(
                workspace_root=workspace_root,
                instruction_path=instruction_path,
                skills_root=None,
                artifacts_dir=artifacts_dir,
                timeout_minutes=1,
            )

            self.assertEqual(result.failure_class, "agent-crash")

    def test_no_external_worktree_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp)
            workspace_root.mkdir()
            project_path = workspace_root / "TPSample"
            project_path.mkdir()
            artifacts_dir = workspace_root / "artifacts"
            artifacts_dir.mkdir()
            instruction_path = workspace_root / "instruction.md"
            instruction_path.write_text("Run tests.", encoding="utf-8")

            subprocess.run(["git", "init"], cwd=project_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "test"], cwd=project_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=project_path, check=True, capture_output=True)

            adapter = KimiCodeAdapter()
            adapter._find_kimi = lambda: Path("/fake/kimi.exe")  # type: ignore[method-assign]

            result = adapter.run(
                workspace_root=workspace_root,
                instruction_path=instruction_path,
                skills_root=None,
                artifacts_dir=artifacts_dir,
                timeout_minutes=1,
            )

            self.assertNotEqual(result.failure_class, "agent-crash")
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/benchmark_runner/test_kimi_code_adapter.py::KimiCodeAdapterPostRunTests -v
```

Expected: FAIL because post-run checks do not exist yet.

- [ ] **Step 3: Implement post-run checks in `adapter.py`**

Add helper functions near `KimiCodeAdapter`:

```python
def _project_uses_external_worktree(project_path: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=str(project_path),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    git_dir = Path(result.stdout.strip())
    try:
        git_dir.relative_to(project_path.resolve())
        return False
    except ValueError:
        return True


def _wait_for_lingering_ue_processes(project_path: Path, max_wait_seconds: float = 600.0) -> bool:
    import time

    project_str = str(project_path.resolve()).lower()
    start = time.perf_counter()
    while True:
        remaining = []
        try:
            output = subprocess.run(
                ["tasklist", "/FO", "CSV", "/V"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            return True

        for line in output.splitlines()[1:]:
            parts = [p.strip('"') for p in line.split("\",\"")]
            if len(parts) < 9:
                continue
            image_name = parts[0].lower()
            command_line = parts[8].lower()
            if image_name == "python.exe" and (project_str in command_line or "autotest.py" in command_line):
                remaining.append(parts[0])
                continue
            if image_name == "unrealeditor-cmd.exe" and project_str in command_line:
                remaining.append(parts[0])

        if not remaining:
            return True
        if time.perf_counter() - start > max_wait_seconds:
            # Kill remaining processes
            for name in remaining:
                subprocess.run(["taskkill", "/F", "/IM", name], capture_output=True)
            return False
        time.sleep(2.0)
```

In `KimiCodeAdapter.run`, after the `subprocess.run(kimi, ...)` call and before returning `AdapterResult`, add:

```python
        if result.returncode == 0 and not timed_out:
            if _project_uses_external_worktree(project_path):
                failure_class = "agent-crash"
            elif not _wait_for_lingering_ue_processes(project_path):
                failure_class = "agent-crash"
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/benchmark_runner/test_kimi_code_adapter.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add benchmarks/ue5-skillsbench/runner/adapter.py tests/benchmark_runner/test_kimi_code_adapter.py
git commit -m "feat(adapter): enforce no external worktrees and wait for lingering UE processes"
```

---

### Task 7: Run full test suite and benchmark smoke

**Files:**
- All modified files.

**Interfaces:**
- Consumes: All implemented changes.
- Produces: Passing tests and benchmark results.

- [ ] **Step 1: Run unit tests**

```bash
python -m pytest tests/benchmark_runner/ -v
```

Expected: All tests PASS.

- [ ] **Step 2: Run a single task smoke test**

```bash
python -m benchmarks.ue5-skillsbench.runner run-single --task-id tps-autotest-fix-failing-error-tests --condition no-skills --adapter oracle --trial 1 --run-id smoke-fix-error-oracle --skip-preflight
```

Expected: Exit code 0.

- [ ] **Step 3: Run the full autotest benchmark matrix**

```bash
python run_autotest_benchmarks.py
```

Expected: The 6 combinations complete; failures are now limited to genuine agent capability issues, not framework misclassification.

- [ ] **Step 4: Commit any final fixes**

If the benchmark smoke reveals any issues, fix them in a follow-up commit.

---

## Self-Review

**Spec coverage:**
- [x] Remove synthetic `(NO TESTS PASSED)` records → Task 1.
- [x] Remove synthetic `(TIMEOUT)` records / filter in parser → Task 1 + Task 2.
- [x] Semantic anti-cheat with meaningful diff → Task 3.
- [x] Clarify `TPSampleTest` module name → Task 4.
- [x] Clarify markdown report requirement → Task 4.
- [x] Prompt-level workspace contract → Task 5.
- [x] Adapter-level lingering process wait → Task 6.
- [x] Adapter-level external worktree detection → Task 6.
- [x] Unit tests for each change → Embedded in each task.
- [x] Integration benchmark rerun → Task 7.

**Placeholder scan:**
- No TBD/TODO.
- No vague "add appropriate error handling" steps.
- All code blocks contain concrete implementation.

**Type consistency:**
- `AdapterResult.failure_class` values used: `"agent-crash"` only.
- Function names consistent across tasks.

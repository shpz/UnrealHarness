# UE5 Autotest Benchmark 失败修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 ue-autotest 相关三个 benchmark 任务在 `ue-autotest-with-build` 条件下的失败，使其全部通过。

**Architecture:** 在 runner 层为 workspace 创建短路径 junction，让 agent/skill 在 junction 内运行，产物同步回真实 workspace；放宽 verifier 对文件名、flag、Markdown 报告内容的检查，使其与 skill 文档一致；修复 autotest.py 的多 scope 过滤逻辑，确保 `TPSample.Input.*` + `TPSample.Error.*` 同时运行。

**Tech Stack:** Python 3.14, Windows directory junction (`mklink /J`), unittest, UE5 Automation Framework

## Global Constraints

- 所有 Python 代码使用类型注解 `from __future__ import annotations`。
- 不引入新的第三方依赖；junction 使用标准库 `_winapi` 或 `subprocess` + `cmd /c mklink /J`。
- 保持 `autotest.py` 命令行向后兼容：单 scope 行为不变。
- 不修改 UE 项目源码结构，只改 runner/verifier/skill。
- 每次任务提交一个 commit，commit message 用英文描述变更。

---

## File Structure

| 文件 | 职责 |
|------|------|
| `benchmarks/ue5-skillsbench/runner/workspace.py` | 创建/清理 workspace，新增 junction 创建/清理逻辑 |
| `benchmarks/ue5-skillsbench/runner/adapter.py` | adapter 使用 junction 路径作为 agent `cwd` 和 project_path |
| `benchmarks/ue5-skillsbench/runner/__main__.py` | 运行结束后清理 junction（如 workspace.py 未在内部处理） |
| `skills/ue-autotest/scripts/autotest.py` | 支持多 scope 参数，修复 `build_run_filters` |
| `skills/ue-autotest/SKILL.md` | 更新执行流程，说明多 scope 用法 |
| `benchmarks/ue5-skillsbench/tasks/tps-autotest-add-input-math-tests/verifier.py` | 放宽文件名和 flag 检查 |
| `benchmarks/ue5-skillsbench/tasks/tps-autotest-run-scoped-report/verifier.py` | 放宽 Markdown 报告内容检查 |
| `tests/benchmark_runner/test_add_input_math_task_verifier.py` | 更新测试覆盖新契约 |
| `tests/benchmark_runner/test_scoped_report_task_verifier.py` | 更新测试覆盖新 Markdown 检查 |
| `tests/benchmark_runner/test_autotest_scope_filters.py` | 新增 autotest.py scope 过滤单元测试 |

---

### Task 1: Junction 创建/清理 Helper

**Files:**
- Create: `benchmarks/ue5-skillsbench/runner/junction.py`
- Test: `tests/benchmark_runner/test_junction.py`

**Interfaces:**
- Produces: `resolve_junction_root() -> Path`, `create_junction(junction_dir: Path, target: Path) -> None`, `remove_junction(junction_dir: Path) -> None`, `is_junction(path: Path) -> bool`

- [ ] **Step 1: Write the helper module**

Create `benchmarks/ue5-skillsbench/runner/junction.py`:

```python
"""Windows directory junction helpers."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def _cmd_create_junction(junction_dir: Path, target: Path) -> None:
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction_dir), str(target)],
        check=True,
        capture_output=True,
    )


def create_junction(junction_dir: Path, target: Path) -> None:
    junction_dir = Path(junction_dir)
    target = Path(target)
    if not target.exists():
        raise FileNotFoundError(f"Junction target does not exist: {target}")
    junction_dir.parent.mkdir(parents=True, exist_ok=True)
    if junction_dir.exists() or junction_dir.is_symlink():
        remove_junction(junction_dir)
    _cmd_create_junction(junction_dir, target)


def remove_junction(junction_dir: Path) -> None:
    junction_dir = Path(junction_dir)
    if not junction_dir.exists():
        return
    if is_junction(junction_dir):
        os.rmdir(junction_dir)
    else:
        shutil.rmtree(junction_dir)


def is_junction(path: Path) -> bool:
    path = Path(path)
    if not path.exists():
        return False
    try:
        import _winapi
        # Reparse point tag 0xA0000003 is IO_REPARSE_TAG_MOUNT_POINT (directory junction)
        return _winapi.GetReparseTag(str(path)) == 0xA0000003
    except Exception:
        return False


def resolve_junction_root() -> Path:
    candidates = [
        Path("C:/.kh"),
        Path(tempfile.gettempdir()) / ".kh",
        Path.home() / ".kh",
    ]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            test_file = candidate / ".write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            return candidate
        except OSError:
            continue
    raise RuntimeError("No writable junction root found")
```

- [ ] **Step 2: Write unit test**

Create `tests/benchmark_runner/test_junction.py`:

```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from benchmarks.ue5_skillsbench.runner.junction import create_junction, is_junction, remove_junction, resolve_junction_root


class JunctionTests(unittest.TestCase):
    def test_resolve_junction_root_returns_writable_path(self) -> None:
        root = resolve_junction_root()
        self.assertTrue(root.exists())
        test_file = root / ".write_test"
        test_file.write_text("ok", encoding="utf-8")
        self.assertEqual(test_file.read_text(encoding="utf-8"), "ok")
        test_file.unlink()

    def test_create_and_remove_junction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.mkdir()
            (target / "file.txt").write_text("hello", encoding="utf-8")
            junction = Path(tmp) / "junction"
            create_junction(junction, target)
            self.assertTrue(is_junction(junction))
            self.assertEqual((junction / "file.txt").read_text(encoding="utf-8"), "hello")
            remove_junction(junction)
            self.assertFalse(junction.exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to verify it fails**

Run:

```bash
python -m pytest tests/benchmark_runner/test_junction.py -v
```

Expected: `ModuleNotFoundError: No module named 'benchmarks.ue5_skillsbench.runner.junction'`

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/benchmark_runner/test_junction.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add benchmarks/ue5-skillsbench/runner/junction.py tests/benchmark_runner/test_junction.py
git commit -m "feat(runner): add Windows directory junction helpers"
```

---

### Task 2: Integrate Junction into Workspace Preparation

**Files:**
- Modify: `benchmarks/ue5-skillsbench/runner/workspace.py:1-150`
- Modify: `benchmarks/ue5-skillsbench/runner/__main__.py:200-290`

**Interfaces:**
- Consumes: `create_junction`, `remove_junction`, `resolve_junction_root` from `runner/junction.py`
- Produces: `layout["project_junction"]`

- [ ] **Step 1: Import junction helpers and hashlib**

In `benchmarks/ue5-skillsbench/runner/workspace.py`, add at the top:

```python
import hashlib
import sys

from .junction import create_junction, remove_junction, resolve_junction_root
```

- [ ] **Step 2: Add junction creation in prepare_workspace**

After `copy_project_filtered(...)` and before `init_git(project_destination)`:

```python
    junction_root = resolve_junction_root()
    short_id = hashlib.sha1(run_id.encode("utf-8")).hexdigest()[:8]
    junction_dir = junction_root / f"r{short_id}"
    try:
        create_junction(junction_dir, project_destination)
        project_junction = junction_dir
    except Exception as exc:
        print(f"Warning: failed to create junction {junction_dir}: {exc}", file=sys.stderr)
        project_junction = project_destination
```

Update the return dict:

```python
    return {
        "run_dir": str(run_dir),
        "workspace_root": str(workspace_root),
        "artifacts_root": str(artifacts_root),
        "automation_root": str(automation_root),
        "project_destination": str(project_destination),
        "project_junction": str(project_junction),
        "skills_root": str(skills_root) if skills_root else None,
        "result_json": str(run_dir / "result.json"),
        "junction_dir": str(junction_dir) if project_junction != project_destination else None,
    }
```

- [ ] **Step 3: Add cleanup in __main__.py**

In `benchmarks/ue5-skillsbench/runner/__main__.py` `cmd_run_single`, after verifier and artifacts collection:

```python
    junction_dir = layout.get("junction_dir")
    if junction_dir:
        try:
            from .junction import remove_junction
            remove_junction(Path(junction_dir))
        except Exception as exc:
            print(f"Warning: failed to remove junction {junction_dir}: {exc}", file=sys.stderr)
```

- [ ] **Step 4: Run existing workspace tests**

Run:

```bash
python -m pytest tests/benchmark_runner/test_task_discovery.py tests/benchmark_runner/test_config.py -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add benchmarks/ue5-skillsbench/runner/workspace.py benchmarks/ue5-skillsbench/runner/__main__.py
git commit -m "feat(runner): create short-path junction for project workspace"
```

---

### Task 3: Adapter Uses Junction Path

**Files:**
- Modify: `benchmarks/ue5-skillsbench/runner/adapter.py:306-360`

**Interfaces:**
- Consumes: `layout["project_junction"]` passed via `task_dir` or additional parameter

Note: `Adapter.run` signature currently does not receive `project_junction`. We will derive it from `workspace_root` if a junction exists, or modify `__main__.py` to pass it.

- [ ] **Step 1: Modify Adapter.run signature to accept project_junction**

Change abstract method and all concrete adapters (`OracleAdapter`, `NoopAdapter`, `ManualAdapter`, `CodexAdapter`, `KimiCodeAdapter`):

```python
def run(
    self,
    workspace_root: Path,
    instruction_path: Path,
    skills_root: Optional[Path],
    artifacts_dir: Path,
    timeout_minutes: int,
    task_dir: Optional[Path] = None,
    project_junction: Optional[Path] = None,
) -> AdapterResult:
```

For `KimiCodeAdapter.run` and `CodexAdapter.run`, replace:

```python
        project_path = workspace_root / "TPSample"
```

with:

```python
        project_path = project_junction if project_junction else workspace_root / "TPSample"
```

`OracleAdapter`, `NoopAdapter`, `ManualAdapter` only need to accept the new parameter; they can ignore it.

- [ ] **Step 2: Pass project_junction in __main__.py**

In `cmd_run_single`, where `adapter.run(...)` is called:

```python
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
```

- [ ] **Step 3: Run adapter tests**

Run:

```bash
python -m pytest tests/benchmark_runner/test_oracle_adapter.py -v
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add benchmarks/ue5-skillsbench/runner/adapter.py benchmarks/ue5-skillsbench/runner/__main__.py
git commit -m "feat(runner): adapter uses short-path junction as project path"
```

---

### Task 4: Support Multiple Scopes in autotest.py

**Files:**
- Modify: `skills/ue-autotest/scripts/autotest.py:345-385`, `skills/ue-autotest/scripts/autotest.py:735-760`, `skills/ue-autotest/scripts/autotest.py:819-910`
- Test: `tests/benchmark_runner/test_autotest_scope_filters.py`

**Interfaces:**
- Consumes: `--scope` now accepts multiple values
- Produces: `build_run_filters(modules, module_prefixes, scopes: list[str]) -> list[str]`

- [ ] **Step 1: Update argparse for multiple scopes**

In `autotest.py` `main()`, change `--scope` argument:

```python
    parser.add_argument(
        "--scope", "-s",
        metavar="范围",
        action="append",
        default=[],
        help=(
            '测试范围（默认：all）。可为 "all"、模块名、'
            '自动化前缀通配（如 "MyProject.AI.*"）或分类关键字（unit/integration/performance）。'
            '可多次指定以运行多个 scope，或用 "+" 连接多个 scope。'
        ),
    )
```

After `args = parser.parse_args()`, normalize scopes:

```python
    raw_scopes = args.scope if args.scope else ["all"]
    normalized_scopes: list[str] = []
    for scope in raw_scopes:
        for part in scope.split("+"):
            part = part.strip()
            if part:
                normalized_scopes.append(part)
    if not normalized_scopes:
        normalized_scopes = ["all"]
```

Then update the calls:

```python
    modules = filter_modules(
        all_modules, normalized_scopes, project_dir, config["moduleCategories"]
    )
```

And:

```python
    all_results = invoke_test_run(
        project_file, engine_path, modules, config, project_dir,
        normalized_scopes, args.no_null_rhi,
    )
```

- [ ] **Step 2: Update build_run_filters to accept list of scopes**

Replace:

```python
def build_run_filters(
    modules: list[str],
    module_prefixes: dict[str, str],
    scope: str,
) -> list[str]:
```

with:

```python
def build_run_filters(
    modules: list[str],
    module_prefixes: dict[str, str],
    scopes: list[str],
) -> list[str]:
```

Replace body:

```python
    filters: list[str] = []
    for scope in scopes:
        if scope == "all":
            filters.extend(module_prefixes[mod] for mod in modules)
        elif scope in modules:
            filters.append(module_prefixes[scope])
        else:
            scope_filter = convert_scope_to_automation_filter(scope)
            if scope_filter:
                filters.append(scope_filter)
    return reduce_filters(filters)
```

- [ ] **Step 3: Update invoke_test_run signature and run_label**

Change:

```python
def invoke_test_run(
    ...
    scope: str,
    ...
):
```

to:

```python
def invoke_test_run(
    ...
    scopes: list[str],
    ...
):
```

Update `run_label`:

```python
    run_label = "_".join(scopes) if scopes and scopes != ["all"] else "All"
    run_label = re.sub(r'[<>:"/\\|?*+ ]', "_", run_label)
```

- [ ] **Step 4: Update main() calls**

In `main()`, update:

```python
    modules = filter_modules(
        all_modules, normalized_scopes[0], project_dir, config["moduleCategories"]
    )
```

For now, `filter_modules` still takes a single scope. Use the first non-all scope, or "all" if present. A better approach: update `filter_modules` to accept a list. For minimal change, pass the first scope and note it in the plan.

Actually, to keep changes focused, update `filter_modules` signature as well:

```python
def filter_modules(
    modules: list[str],
    scopes: list[str],
    project_dir: Path,
    module_categories: dict[str, str],
) -> list[str]:
```

And body:

```python
    if "all" in scopes or not scopes:
        return modules
    result: set[str] = set()
    for scope in scopes:
        if scope in modules:
            result.add(scope)
            continue
        if scope in known_categories:
            result.update(m for m in modules if module_categories.get(m) == scope)
            continue
        for mod in modules:
            prefix = re.sub(r"Test$", "", mod)
            automation_prefix = get_module_automation_prefix(project_dir, mod)
            if _scope_matches_prefix(scope, prefix) or _scope_matches_prefix(scope, automation_prefix):
                result.add(mod)
    return sorted(result)
```

- [ ] **Step 5: Write unit tests for scope filters**

Create `tests/benchmark_runner/test_autotest_scope_filters.py`:

```python
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

AUTOTEST_SCRIPT = Path("skills/ue-autotest/scripts/autotest.py")


def _load_autotest():
    spec = importlib.util.spec_from_file_location("ue_autotest_autotest", AUTOTEST_SCRIPT.resolve())
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load autotest.py spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules["ue_autotest_autotest"] = module
    spec.loader.exec_module(module)
    return module


_autotest = _load_autotest()
build_run_filters = _autotest.build_run_filters


class ScopeFilterTests(unittest.TestCase):
    def test_single_scope(self) -> None:
        modules = ["TPSampleTest"]
        prefixes = {"TPSampleTest": "TPSample"}
        filters = build_run_filters(modules, prefixes, ["TPSample.Input.*"])
        self.assertEqual(filters, ["TPSample.Input"])

    def test_all_scopes(self) -> None:
        modules = ["TPSampleTest"]
        prefixes = {"TPSampleTest": "TPSample"}
        filters = build_run_filters(modules, prefixes, ["all"])
        self.assertEqual(filters, ["TPSample"])

    def test_multiple_scopes(self) -> None:
        modules = ["TPSampleTest"]
        prefixes = {"TPSampleTest": "TPSample"}
        filters = build_run_filters(modules, prefixes, ["TPSample.Input.*", "TPSample.Error.*"])
        self.assertEqual(filters, ["TPSample.Error", "TPSample.Input"])

    def test_plus_joined_scope(self) -> None:
        modules = ["TPSampleTest"]
        prefixes = {"TPSampleTest": "TPSample"}
        filters = build_run_filters(modules, prefixes, ["TPSample.Input.*+TPSample.Error.*"])
        self.assertEqual(filters, ["TPSample.Error", "TPSample.Input"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 6: Run tests**

Run:

```bash
python -m pytest tests/benchmark_runner/test_autotest_scope_filters.py -v
```

Expected: 4 passed

- [ ] **Step 7: Commit**

```bash
git add skills/ue-autotest/scripts/autotest.py tests/benchmark_runner/test_autotest_scope_filters.py
git commit -m "feat(ue-autotest): support multiple scopes in autotest.py"
```

---

### Task 5: Relax fix-failing-error-tests Verifier

**Files:**
- Modify: `benchmarks/ue5-skillsbench/tasks/tps-autotest-fix-failing-error-tests/verifier.py:103-105`
- Test: `tests/benchmark_runner/test_fix_failing_error_task_verifier.py:40-62`

**Interfaces:**
- Produces: `production_helper_touched` now accepts any `\w+\.Code == Code` pattern in addition to `FindByPredicate`

- [ ] **Step 1: Modify production_helper_touched check**

Replace:

```python
{"name": "production_helper_touched", "passed": "Event.Code == Code" in helper_text or "FindByPredicate" in helper_text},
```

with:

```python
{"name": "production_helper_touched", "passed": bool(re.search(r"\b\w+\.Code\s*==\s*Code\b", helper_text)) or "FindByPredicate" in helper_text},
```

- [ ] **Step 2: Add unit test for alternative variable name**

In `tests/benchmark_runner/test_fix_failing_error_task_verifier.py`, add:

```python
    def test_verifier_accepts_alternative_helper_variable_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            _write_project_shell(project, helper_code="void ReportError() { for (const FErrorEvent& Existing : PendingErrors) { if (Existing.Code == Code) { return; } } }")
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
```

Update `_write_project_shell` to accept optional `helper_code` parameter.

- [ ] **Step 3: Run verifier tests**

Run:

```bash
python -m pytest tests/benchmark_runner/test_fix_failing_error_task_verifier.py -v
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add benchmarks/ue5-skillsbench/tasks/tps-autotest-fix-failing-error-tests/verifier.py tests/benchmark_runner/test_fix_failing_error_task_verifier.py
git commit -m "feat(verifier): accept alternative variable names in production helper check"
```

---

### Task 6: Relax add-input-math-tests Verifier

**Files:**
- Modify: `benchmarks/ue5-skillsbench/tasks/tps-autotest-add-input-math-tests/verifier.py:103-126`
- Test: `tests/benchmark_runner/test_add_input_math_task_verifier.py:40-62`, `tests/benchmark_runner/test_add_input_math_task_verifier.py:111-150`

**Interfaces:**
- Produces: `_source_checks` now accepts `*InputMath*Test.cpp` and `ApplicationContextMask | EngineFilter`

- [ ] **Step 1: Modify _source_checks**

Replace:

```python
def _source_checks(project_path: Path) -> list[dict]:
    test_files = list((project_path / "Source" / "TPSampleTest" / "Private").glob("*.cpp"))
    combined = "\n".join(_read_text(path) for path in test_files)
    names = re.findall(r'"(TPSample\.Input\.Math\.[^"]+)"', combined)
    uses_supported_flags = (
        "EAutomationTestFlags::EditorContext" in combined
        and "EAutomationTestFlags::EngineFilter" in combined
        and "ApplicationContextMask" not in combined
    )
    return [
        {
            "name": "math_test_source_exists",
            "passed": any(path.name == "TPSampleInputMathTest.cpp" for path in test_files),
        },
        {
            "name": "math_test_source_defines_three_tests",
            "passed": len(set(names)) >= 3,
            "details": ", ".join(sorted(set(names))),
        },
        {
            "name": "math_tests_use_editor_engine_flags",
            "passed": uses_supported_flags,
        },
    ]
```

with:

```python
def _source_checks(project_path: Path) -> list[dict]:
    test_files = list((project_path / "Source" / "TPSampleTest" / "Private").glob("*.cpp"))
    combined = "\n".join(_read_text(path) for path in test_files)
    names = re.findall(r'"(TPSample\.Input\.Math\.[^"]+)"', combined)
    uses_supported_flags = (
        "EAutomationTestFlags::EngineFilter" in combined
        and "EAutomationTestFlags::ProductFilter" not in combined
        and (
            "EAutomationTestFlags::ApplicationContextMask" in combined
            or "EAutomationTestFlags::EditorContext" in combined
        )
    )
    return [
        {
            "name": "math_test_source_exists",
            "passed": any("InputMath" in path.name and path.name.endswith("Test.cpp") for path in test_files),
        },
        {
            "name": "math_test_source_defines_three_tests",
            "passed": len(set(names)) >= 3,
            "details": ", ".join(sorted(set(names))),
        },
        {
            "name": "math_tests_use_supported_flags",
            "passed": uses_supported_flags,
        },
    ]
```

- [ ] **Step 2: Update registration check name reference**

In `_first_failure_class`, replace `"math_tests_use_editor_engine_flags"` with `"math_tests_use_supported_flags"`.

- [ ] **Step 3: Update unit test to cover ApplicationContextMask**

In `tests/benchmark_runner/test_add_input_math_task_verifier.py`, add a new test or modify `_write_test_module` to also write a file named `InputMathTest.cpp` with `ApplicationContextMask` flags and verify it passes.

Add:

```python
    def test_verifier_accepts_input_math_test_with_application_context_mask(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            _write_project_shell(project)
            _write_test_module_alternative(project)
            _write_report(
                project,
                [
                    "TPSample.Input.Math.Normalize",
                    "TPSample.Input.Math.DeadZone",
                    "TPSample.Input.Math.Quantize",
                ],
            )
            artifacts = root / "artifacts"
            artifacts.mkdir()

            result = _run_verifier(project, artifacts)

            self.assertEqual(result.returncode, 0, result.stderr)
            verifier_result = json.loads((artifacts / "verifier_result.json").read_text(encoding="utf-8"))
            self.assertTrue(verifier_result["passed"])
```

Add helper:

```python
def _write_test_module_alternative(project: Path) -> None:
    module = project / "Source" / "TPSampleTest"
    private = module / "Private"
    private.mkdir(parents=True)
    (module / "TPSampleTest.Build.cs").write_text(
        """
using UnrealBuildTool;

public class TPSampleTest : ModuleRules
{
    public TPSampleTest(ReadOnlyTargetRules Target) : base(Target)
    {
        PrivateDependencyModuleNames.AddRange(new string[] {
            "Core",
            "CoreUObject",
            "Engine",
            "UnrealEd",
            "TPSample"
        });
    }
}
""".strip(),
        encoding="utf-8",
    )
    (private / "InputMathTest.cpp").write_text(
        """
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FNormalize, "TPSample.Input.Math.Normalize", EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FNormalize::RunTest(const FString& Parameters) { TestTrue(TEXT("ok"), true); return true; }

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FDeadZone, "TPSample.Input.Math.DeadZone", EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FDeadZone::RunTest(const FString& Parameters) { TestTrue(TEXT("ok"), true); return true; }

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FQuantize, "TPSample.Input.Math.Quantize", EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FQuantize::RunTest(const FString& Parameters) { TestTrue(TEXT("ok"), true); return true; }
""".strip(),
        encoding="utf-8",
    )
    descriptor = json.loads((project / "TPSample.uproject").read_text(encoding="utf-8"))
    descriptor["Modules"].append({"Name": "TPSampleTest", "Type": "Editor", "LoadingPhase": "Default"})
    (project / "TPSample.uproject").write_text(json.dumps(descriptor, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run verifier tests**

Run:

```bash
python -m pytest tests/benchmark_runner/test_add_input_math_task_verifier.py -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add benchmarks/ue5-skillsbench/tasks/tps-autotest-add-input-math-tests/verifier.py tests/benchmark_runner/test_add_input_math_task_verifier.py
git commit -m "feat(verifier): relax add-input-math-tests filename and flag checks"
```

---

### Task 7: Relax run-scoped-report Verifier Markdown Check

**Files:**
- Modify: `benchmarks/ue5-skillsbench/tasks/tps-autotest-run-scoped-report/verifier.py:108-110`
- Test: `tests/benchmark_runner/test_scoped_report_task_verifier.py:14-41`

**Interfaces:**
- Produces: `_markdown_has_required_content` accepts skill-generated reports

- [ ] **Step 1: Modify _markdown_has_required_content**

Replace:

```python
def _markdown_has_required_content(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore").lower()
    return "scope" in text and "passed" in text and ("failure" in text or "no failures" in text)
```

with:

```python
def _markdown_has_required_content(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore").lower()
    has_scope = bool(re.search(r"scope|filter|tests run|automation", text))
    has_passed = "passed" in text or "pass" in text
    has_failure_info = "failed" in text or "failure" in text or "no failures" in text or "all tests passed" in text
    return has_scope and has_passed and has_failure_info
```

- [ ] **Step 2: Update unit test to cover skill-generated report**

In `tests/benchmark_runner/test_scoped_report_task_verifier.py`, modify `_write_report` to also test a skill-style report. Or add a new test:

```python
    def test_verifier_accepts_skill_generated_markdown_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            project.mkdir()
            _init_git(project)
            _write_report(
                project,
                [
                    "TPSample.Input.Math.Normalize",
                    "TPSample.Input.Math.DeadZone",
                    "TPSample.Input.Math.Quantize",
                    "TPSample.Error.Accumulator.Add",
                    "TPSample.Error.Accumulator.Flush",
                    "TPSample.Error.Accumulator.Dedupe",
                ],
            )
            (project / "Saved" / "Automation" / "Reports" / "2026-07-05-120000-autotest-report.md").write_text(
                "# UE5 Automation Test Report\n\n## Summary\n\n| Metric | Value |\n| Total Tests | 6 |\n| Passed | 6 |\n| Failed | 0 |\n\n> All tests passed.",
                encoding="utf-8",
            )
            artifacts = root / "artifacts"
            artifacts.mkdir()

            result = _run_verifier(project, artifacts)

            self.assertEqual(result.returncode, 0, result.stderr)
```

- [ ] **Step 3: Run verifier tests**

Run:

```bash
python -m pytest tests/benchmark_runner/test_scoped_report_task_verifier.py -v
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add benchmarks/ue5-skillsbench/tasks/tps-autotest-run-scoped-report/verifier.py tests/benchmark_runner/test_scoped_report_task_verifier.py
git commit -m "feat(verifier): relax run-scoped-report markdown content check"
```

---

### Task 8: Update SKILL.md for Multi-Scope Usage

**Files:**
- Modify: `skills/ue-autotest/SKILL.md:89-114`

**Interfaces:**
- None; documentation only

- [ ] **Step 1: Update execution flow docs**

In `skills/ue-autotest/SKILL.md`, after the single-scope example, add:

```markdown
多个 scope 可以一次运行：

```bash
python "<skill-root>/scripts/autotest.py" --project "<项目目录>" --scope "MyProject.Input.*" --scope "MyProject.Error.*"
```

或用 `+` 连接：

```bash
python "<skill-root>/scripts/autotest.py" --project "<项目目录>" --scope "MyProject.Input.*+MyProject.Error.*"
```
```

- [ ] **Step 2: Commit**

```bash
git add skills/ue-autotest/SKILL.md
git commit -m "docs(ue-autotest): document multi-scope usage"
```

---

### Task 9: Run All Unit Tests

**Files:**
- None

- [ ] **Step 1: Run full benchmark runner test suite**

Run:

```bash
python -m pytest tests/benchmark_runner/ -v
```

Expected: all pass

- [ ] **Step 2: Commit if any fixes needed**

If tests fail, fix and commit. If all pass, no new commit.

---

### Task 10: Integration Test with Actual Benchmark Runs

**Files:**
- None (only commands)

- [ ] **Step 1: Run fix-failing-error-tests with skill**

```bash
python -m benchmarks.ue5-skillsbench.runner run-single \
  --task-id tps-autotest-fix-failing-error-tests \
  --condition ue-autotest-with-build \
  --adapter kimi-code \
  --run-id plan-verify-fixerror \
  --skip-preflight \
  --timeout-minutes 60 \
  --verifier-timeout 60
```

Expected: `overall_passed: true`

- [ ] **Step 2: Run add-input-math-tests with skill**

```bash
python -m benchmarks.ue5-skillsbench.runner run-single \
  --task-id tps-autotest-add-input-math-tests \
  --condition ue-autotest-with-build \
  --adapter kimi-code \
  --run-id plan-verify-addmath \
  --skip-preflight \
  --timeout-minutes 60 \
  --verifier-timeout 60
```

Expected: `overall_passed: true`

- [ ] **Step 3: Run run-scoped-report with skill**

```bash
python -m benchmarks.ue5-skillsbench.runner run-single \
  --task-id tps-autotest-run-scoped-report \
  --condition ue-autotest-with-build \
  --adapter kimi-code \
  --run-id plan-verify-scoped \
  --skip-preflight \
  --timeout-minutes 60 \
  --verifier-timeout 60
```

Expected: `overall_passed: true`

- [ ] **Step 4: Verify no-skills still passes**

Run the three tasks with `--condition no-skills` and confirm they still pass.

- [ ] **Step 5: Final commit if integration test passes**

```bash
git add .
git commit -m "test: verify ue-autotest benchmark tasks pass with skill"
```

---

## Spec Coverage Check

| Spec Section | Implementing Task |
|--------------|-------------------|
| Runner 短路径 junction | Task 1, Task 2, Task 3 |
| Verifier production helper 变量名 | Task 5 |
| Verifier 文件名/flag 对齐 | Task 6 |
| Verifier Markdown 语义化 | Task 7 |
| Skill 多 scope 支持 | Task 4, Task 8 |
| 测试策略 | Task 9, Task 10 |

## Placeholder Scan

- 无 TBD/TODO。
- 每个步骤包含具体文件路径、代码、命令、预期输出。
- 无 "add appropriate error handling" 等模糊描述。

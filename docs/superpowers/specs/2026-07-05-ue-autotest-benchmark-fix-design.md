# UE5 Autotest Benchmark 失败修复设计

## 1. 目标与范围

修复 `ue-autotest-with-build` 条件下三个 benchmark 任务的失败，使其全部通过：

- `tps-autotest-fix-failing-error-tests`
- `tps-autotest-add-input-math-tests`
- `tps-autotest-run-scoped-report`

本变更只涉及 runner、verifier 与 `skills/ue-autotest`，不修改 UE 项目源码结构。

## 2. 失败根因

1. **Windows 长路径限制**：agent/skill 在深层 workspace 路径下运行 UE5 构建与 Automation Test，路径长度触及 Windows 限制，导致文件操作或命令行参数失败。
2. **Verifier 检查过严**：
   - `add-input-math-tests` 要求源文件必须名为 `TPSampleInputMathTest.cpp`，且只接受 `EditorContext | EngineFilter` 的 flag 组合；与 skill 文档和实际生成代码不一致。
   - `run-scoped-report` 要求 Markdown 报告必须同时出现 `scope`、`passed` 与 `failure/no failures`，对 skill 生成的表格摘要报告过于严格。
3. **autotest.py 不支持多 scope**：`--scope` 只接受单个值，无法同时运行 `TPSample.Input.*` 与 `TPSample.Error.*`。

## 3. 设计概览

新增一层 **短路径 junction**：runner 在 prepare workspace 时为项目目录创建 Windows directory junction（类似符号链接，但无需管理员权限），junction 路径短且确定；adapter 将 junction 路径作为 agent 的 `cwd` 与 `project_path`；agent 在此短路径内完成构建与测试，产物通过 junction 自动同步回真实 workspace。

同步放宽两个 verifier 的判定条件，使其与 skill 实际行为一致。

修改 `autotest.py` 的 argparse 与 filter 逻辑，支持一次传入多个 scope（多次 `--scope` 或用 `+` 连接），并保持单 scope 向后兼容。

## 4. 组件与接口

### 4.1 `runner/junction.py`（新增）

提供 Windows directory junction 的创建、删除与检测：

- `resolve_junction_root() -> Path`：按 `C:/.kh` → `%TEMP%/.kh` → `~/.kh` 顺序寻找可写根目录。
- `create_junction(junction_dir: Path, target: Path) -> None`：清理旧 junction 后创建新 junction。
- `remove_junction(junction_dir: Path) -> None`：安全删除 junction（junction 用 `os.rmdir`，普通目录用 `shutil.rmtree`）。
- `is_junction(path: Path) -> bool`：使用 `_winapi.GetReparseTag` 判断 reparse tag 是否为 `IO_REPARSE_TAG_MOUNT_POINT`。

### 4.2 `runner/workspace.py`

`prepare_workspace` 在复制项目后创建 junction，并在返回的 layout 中新增：

- `project_junction`：指向项目目录的 junction 路径（agent 应使用的路径）。由于 junction 直接指向 `project_destination`（即 `workspace_root / "TPSample"`），所以 `project_junction` 等于 `junction_dir`。
- `junction_dir`：junction 根目录，用于运行结束后清理。

若创建 junction 失败，回退到真实 `project_destination` 路径，保证可用性。

### 4.3 `runner/adapter.py`

`Adapter.run` 抽象方法新增可选参数 `project_junction: Optional[Path]`；`KimiCodeAdapter` 与 `CodexAdapter` 优先使用 `project_junction` 作为 `project_path`，未提供时回退到 `workspace_root / "TPSample"`。`OracleAdapter`、`NoopAdapter`、`ManualAdapter` 仅接受参数，不做使用。

### 4.4 `runner/__main__.py`

`cmd_run_single` 在 verifier 与产物收集完成后，若 layout 中存在 `junction_dir`，调用 `remove_junction` 清理。失败仅打印 warning，不影响 benchmark 结果。

### 4.5 `skills/ue-autotest/scripts/autotest.py`

- `--scope` 改为 `action="append"`，支持多次指定。
- 解析后用 `+` 拆分并去重，得到 `normalized_scopes: list[str]`。
- `filter_modules` 与 `build_run_filters` 改为接受 `scopes: list[str]`：
  - `all` 保留全部模块。
  - 模块名、category、通配前缀均逐个 scope 匹配，结果取并集。
  - `build_run_filters` 对生成的 filter 去重排序，返回列表。
- `invoke_test_run` 的 `run_label` 由多个 scope 拼接生成，并替换非法文件名字符。
- 更新 `skills/ue-autotest/SKILL.md`，补充多 scope 用法的命令行示例。

### 4.6 Verifier 放宽

- `tps-autotest-fix-failing-error-tests/verifier.py`：
  - `production_helper_touched` 检查从只接受固定字符串 `Event.Code == Code` 或 `FindByPredicate`，放宽为接受任意 `<变量>.Code == Code` 模式，以便认可 agent 使用不同变量名（如 `Existing.Code == Code`）实现的等价去重逻辑。
- `tps-autotest-add-input-math-tests/verifier.py`：
  - 文件名检查改为 `*InputMath*Test.cpp`。
  - flag 检查改为必须包含 `EngineFilter`，禁止 `ProductFilter`，并允许 `ApplicationContextMask | EngineFilter` 或 `EditorContext | EngineFilter`；同时接受 `EAutomationTestFlags_XXX` 宏形式与 `EAutomationTestFlags::XXX` 枚举形式。
- `tps-autotest-run-scoped-report/verifier.py`：
  - Markdown 内容检查改为：包含 `scope/filter/tests run/automation` 之一、包含 `passed/pass`、包含 `failed/failure/no failures/all tests passed` 之一。

## 5. 数据流

1. `run-single` 调用 `prepare_workspace` 复制项目到深层 workspace。
2. `prepare_workspace` 创建短路径 junction，返回 `project_junction` 与 `junction_dir`。
3. `adapter.run` 使用 `project_junction` 作为 agent 工作目录与项目路径。
4. agent/skill 在 junction 内编译、运行测试；文件系统变更通过 junction 同步回真实 workspace。
5. verifier 在真实 workspace 上检查产物（源文件、报告等）。
6. `run-single` 运行结束后删除 junction。

## 6. 错误处理

- junction 创建失败：打印 warning，回退到真实路径。
- junction 删除失败：打印 warning，不中断退出。
- `autotest.py` 多 scope 解析：空 scope 列表自动回退到 `["all"]`。
- 所有新增 Python 代码使用类型注解 `from __future__ import annotations`。

## 7. 测试策略

| 测试层级 | 内容 |
|----------|------|
| 单元测试 | `test_junction.py`：junction 创建/删除/检测；`test_autotest_scope_filters.py`：单 scope、多 scope、`+` 连接、all；更新 `test_add_input_math_task_verifier.py` 与 `test_scoped_report_task_verifier.py` 覆盖新契约。 |
| 集成测试 | 在 `ue-autotest-with-build` 与 `no-skills` 条件下分别运行三个任务，确认 `overall_passed: true`。 |
| 回归测试 | 运行 `python -m pytest tests/benchmark_runner/ -v`，确保未改动任务的 verifier 与 adapter 行为不变。 |

## 8. 提交策略

按任务分 commit，每个 commit 聚焦一个独立变更：

1. `feat(runner): add Windows directory junction helpers`
2. `feat(runner): create short-path junction for project workspace`
3. `feat(runner): adapter uses short-path junction as project path`
4. `feat(ue-autotest): support multiple scopes in autotest.py`
5. `feat(verifier): relax add-input-math-tests filename and flag checks`
6. `feat(verifier): relax run-scoped-report markdown content check`
7. `docs(ue-autotest): document multi-scope usage`
8. `test: verify ue-autotest benchmark tasks pass with skill`

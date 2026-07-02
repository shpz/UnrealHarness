# ue-autotest 基准测试任务设计

日期：2026-07-02

> 注：三个任务的**实现顺序**以 [`ue5-skillsbench-framework-completion-design.md`](./ue5-skillsbench-framework-completion-design.md) 为准（`run-scoped-report` 先行，优先打通 Automation report 管线），本文中的任务编号顺序不代表实现顺序。condition 矩阵也以该文档为准。

本文设计 3 个面向 `ue-autotest` skill 的 `ue5-skillsbench` 任务。目标不是直接实现任务，而是定义后续应落到 `benchmarks/ue5-skillsbench/tasks/<id>/` 下的 `task.toml`、`instruction.md`、`setup.py`、`verifier.py`、oracle patch 和 artifacts 约束。

现有 benchmark 框架约定：

- 基线项目使用 `sample/TPSample`，trial 在隔离 workspace 中运行。
- 每个任务目录包含 `task.toml`、`instruction.md`、`setup.py`、`verifier.py`。
- `verifier.py` 通过 `PROJECT_PATH`、`ARTIFACTS_PATH`、`BENCHMARK_ROOT` 获取运行上下文，并写出 `verifier_result.json`。
- verifier 只能检查最终项目状态和运行产物，不读取 skill 目录，也不依赖 agent 的过程声明。
- 运行产物应进入 artifacts，例如 `build.log`、`Saved/Automation/autotest_results.json`、UE 原生 Automation report、Markdown 报告和 verifier 日志。

## 任务矩阵

| 任务 ID | 难度 | 核心能力 | 主要失败类型 |
| --- | --- | --- | --- |
| `tps-autotest-add-input-math-tests` | medium | 为无测试模块项目创建并注册 UE Automation Test | 测试模块缺失、注册错误、测试数量不足、Automation 未运行 |
| `tps-autotest-fix-failing-error-tests` | medium-hard | 根据失败报告闭环修复测试或被测代码中的明确缺陷 | 编译失败、断言失败、弱化测试、未重跑同一 scope |
| `tps-autotest-run-scoped-report` | medium | 使用 scope/category 运行已有测试并产出可追溯报告 | scope 错误、重复启动、报告缺失、失败摘要不完整 |

`benchmark.yaml` 后续应补充：

```yaml
skills:
  ue-build:
    path: skills/ue-build
  ue-autotest:
    path: skills/ue-autotest

conditions:
  - id: no-skills
    skills: []
  - id: ue-build-only
    skills: [ue-build]
  - id: ue-autotest-with-build
    skills: [ue-build, ue-autotest]
```

## 共同 verifier 要求

所有 `ue-autotest` 任务的 verifier 应执行以下通用检查：

1. 构建 `TPSampleEditor Win64 Development`。
2. 使用 `UnrealEditor-Cmd.exe` 运行目标 Automation scope。
3. 优先解析 UE 原生 `Saved/Automation/Reports/Raw/<Scope>/index.json`；缺失时可解析 `Saved/Automation/autotest_results.json` 或日志，但必须把回退路径写入 `checks`。
4. 写出统一结构的 `verifier_result.json`：`passed`、`failure_class`、`checks`、`automation`、`artifacts`。
5. 复制或记录 Automation 原生报告、`autotest_results.json`、Markdown 报告、编辑器日志和 verifier stdout/stderr。

建议 `failure_class`：

- `build`：项目或测试模块无法编译。
- `registration`：测试模块未在 `.uproject` 或 Editor target 注册。
- `automation-discovery`：目标 scope 测试数量为 0 或少于要求。
- `test`：Automation 测试失败。
- `reporting`：测试通过但结构化结果或 Markdown 报告缺失。
- `verifier-error`：verifier 自身异常或无法解析必要产物。

## 任务 1：新增输入数学测试

### 基本信息

- ID：`tps-autotest-add-input-math-tests`
- primary skills：`["ue-autotest"]`
- secondary skills：`["ue-build"]`
- difficulty：`medium`
- subcategory：`automation-test-authoring`
- tags：`["unreal-engine", "ue5", "automation", "test-module", "headless"]`

### 用户指令意图

`instruction.md` 面向 agent 只描述产品目标，不泄露 verifier 细节：

> 为 TPSample 新增 UE Automation tests，覆盖输入向量归一化与死区处理。需要创建必要的 Editor test module，至少包含 happy path、edge、regression 三个测试，并无头运行通过。

不在指令中直接说“使用 ue-autotest”，由条件注入 skill 决定 agent 是否能发现正确流程。

### setup fixture

`setup.py` 在 trial workspace 中注入纯 C++ helper：

- `Source/TPSample/Public/TPSampleInputMath.h`
- `Source/TPSample/Private/TPSampleInputMath.cpp`

helper 提供无 World 依赖的函数，例如：

- `NormalizeMoveInput(FVector2D RawInput, float DeadZone)`
- `QuantizeLookInput(FVector2D RawInput, float Step)`
- `IsInputWithinDeadZone(FVector2D RawInput, float DeadZone)`

fixture 要保证 oracle 前 verifier 失败：项目可编译，但没有任何 `TPSample.Input.*` Automation tests。

### 期望 agent 行为

- 创建 `Source/TPSampleTest/` Editor 测试模块。
- 在 `.uproject` 注册 `TPSampleTest`，类型为 `Editor`。
- 在 `TPSampleEditor.Target.cs` 的 `ExtraModuleNames` 中加入 `TPSampleTest`。
- `TPSampleTest.Build.cs` 只依赖必要模块：`Core`、`CoreUObject`、`Engine`、`UnrealEd`、`TPSample`。
- 新增 `Private/TPSampleInputMathTest.cpp`。
- 使用 `IMPLEMENT_SIMPLE_AUTOMATION_TEST` 和 `ApplicationContextMask | EngineFilter`。
- 测试命名使用 `TPSample.Input.Math.<Scenario>`，至少包含 3 个测试：normalization happy path、dead-zone edge、quantization regression。
- 运行新增 scope，例如 `TPSample.Input.Math.*`，并产出报告。

### verifier 检查

- `Source/TPSampleTest/TPSampleTest.Build.cs` 存在。
- `.uproject` 包含 `TPSampleTest` Editor module。
- `TPSampleEditor.Target.cs` 包含 `TPSampleTest`，Game target 不包含该模块。
- 构建通过。
- Automation scope `TPSample.Input.Math.*` 至少发现 3 个测试。
- 目标测试全部通过，且没有 skipped/not-run。
- 产物中存在结构化结果和原生或 Markdown 报告。

### oracle 解法形状

oracle patch 应包含完整测试模块注册和三个最小测试。oracle 不应修改 helper 行为，也不应把测试模块加入 Game target。

### 评分指标

- test authoring success：模块、注册、命名、断言是否符合要求。
- headless execution success：是否真实运行目标 scope。
- minimality：是否避免 PIE、viewport、渲染或不必要依赖。

## 任务 2：修复失败的错误处理测试

### 基本信息

- ID：`tps-autotest-fix-failing-error-tests`
- primary skills：`["ue-autotest"]`
- secondary skills：`["ue-build"]`
- difficulty：`medium-hard`
- subcategory：`automation-failure-repair`
- tags：`["unreal-engine", "ue5", "automation", "debugging", "regression"]`

### 用户指令意图

> 项目里已有一组 UE Automation tests 失败。请运行相关测试，阅读失败报告，修复根因，然后重新运行同一 scope 直到通过。不要删除测试或降低断言强度。

### setup fixture

`setup.py` 注入一个已有测试模块和一个带缺陷的纯 C++ 错误聚合 helper：

- `Source/TPSample/Public/TPSampleErrorAccumulator.h`
- `Source/TPSample/Private/TPSampleErrorAccumulator.cpp`
- `Source/TPSampleTest/TPSampleTest.Build.cs`
- `Source/TPSampleTest/Private/TPSampleErrorAccumulatorTest.cpp`
- `.uproject` 和 `TPSampleEditor.Target.cs` 已完成测试模块注册。

缺陷建议：`ReportError` 对同一 error code 重复广播，导致 regression 测试期望一次广播但实际多次广播。测试使用 `UErrorTestHelper` 记录 `BroadcastCount`。

fixture 要保证 oracle 前：项目能编译，Automation scope `TPSample.Error.Accumulator.*` 至少 3 个测试中 1 个失败。

### 期望 agent 行为

- 运行 `TPSample.Error.Accumulator.*` 或对应模块 scope。
- 阅读 `autotest_results.json`、原生 report 或编辑器日志定位失败断言。
- 判断失败来自生产 helper 的明确 bug，而不是测试预期错误。
- 最小修改 `TPSampleErrorAccumulator.cpp`，修复重复广播。
- 保留原测试和断言，不注释、不删除、不放宽通过条件。
- 重新运行同一 scope 并确认通过。

### verifier 检查

- 目标测试文件仍存在，目标测试名仍存在。
- 断言文本或关键条件未被删除，例如 `BroadcastCount == 1` 仍可检测。
- 生产 helper 修复后构建通过。
- `TPSample.Error.Accumulator.*` 至少发现 3 个测试并全部通过。
- verifier 可额外用源码静态检查拒绝明显作弊：删除测试、把 `return true` 提前、把期望值改为错误实际值、扩大容差到无意义范围。

### oracle 解法形状

oracle patch 只修复错误去重逻辑，例如记录已广播 error code 或在同一 flush 周期内 dedupe。测试文件不应变更，除非 fixture 中确实有拼写或编译错误。

### 评分指标

- repair fidelity：是否修根因而非改测试。
- loop discipline：是否基于报告定位并重跑同一 scope。
- redline compliance：是否遵守不删测试、不弱化断言。

## 任务 3：按 scope 运行并生成报告

### 基本信息

- ID：`tps-autotest-run-scoped-report`
- primary skills：`["ue-autotest"]`
- secondary skills：`["ue-build"]`
- difficulty：`medium`
- subcategory：`automation-execution-reporting`
- tags：`["unreal-engine", "ue5", "automation", "scope", "reporting"]`

### 用户指令意图

> 项目已经有多个 UE Automation test scope。请只运行输入和错误处理相关测试，不运行性能测试，输出通过/失败摘要，并告诉我报告文件路径。

该任务评估 `ue-autotest` 的执行和报告能力，而不是测试编写能力。

### setup fixture

`setup.py` 注入一个已注册的 `TPSampleTest` 模块，包含三组测试：

- `TPSample.Input.Math.*`：3 个 passing tests。
- `TPSample.Error.Accumulator.*`：3 个 passing tests。
- `TPSample.Performance.Memory.*`：1 个 passing test，但不应被本任务运行。

可选：在 `skills/ue-autotest/config.yaml` 机制对应的项目侧配置中声明分类映射，但 verifier 不应依赖 skill 文件。更稳妥的做法是让用户指令明确“输入和错误处理相关测试”，期望 agent 使用 `TPSample.Input.*+TPSample.Error.*` 或等价多过滤器一次运行。

### 期望 agent 行为

- 不修改生产或测试代码。
- 构建后运行指定 scope：`TPSample.Input.*` 和 `TPSample.Error.*`。
- 避免运行 `TPSample.Performance.*`。
- 单次或最少次数启动 Editor，避免对每个测试单独启动。
- 产出 `Saved/Automation/autotest_results.json` 和 Markdown 报告。
- 在最终回复中包含总数、通过数、失败数、scope 和报告路径。

### verifier 检查

- git diff 中没有源码变更，或仅允许 Automation 产物变更。
- Automation 结果包含 Input 和 Error 两组测试，合计至少 6 个。
- Automation 结果不包含 `TPSample.Performance.*`。
- 所有运行的目标测试通过。
- Markdown 报告存在并包含 scope、pass/fail 统计、失败摘要段落或明确的“无失败”说明。
- artifacts 中有编辑器日志和结构化结果。

### oracle 解法形状

oracle 不需要源码 patch；oracle action 是正确运行命令并保留产物。若 benchmark 框架必须以 patch 表示 oracle，则 oracle patch 应为空，oracle verifier 通过依赖 setup 后直接执行推荐命令。

### 评分指标

- scope precision：是否只运行要求 scope。
- reporting completeness：报告路径、统计、失败摘要是否完整。
- efficiency：是否避免无意义重复启动 Editor。

## 实现顺序建议

1. 先实现 `tps-autotest-add-input-math-tests`，它复用既有 Phase 05 思路，是 `ue-autotest` 的核心新增测试能力。
2. 再实现 `tps-autotest-run-scoped-report`，验证脚本执行和报告产物，不依赖复杂修复。
3. 最后实现 `tps-autotest-fix-failing-error-tests`，它对 verifier 防作弊和失败分类要求最高。

## 验收标准

- 每个任务 oracle 前 verifier 必须失败或在报告任务中缺少必要产物。
- 应用 oracle 或执行 oracle action 后 verifier 必须通过。
- 每个 oracle 连续运行 3 次均通过。
- `no-skills` 与 `ue-autotest-with-build` 条件应形成可观察差异。
- verifier 不读取 skill 目录，不把实现细节写入用户指令。
- artifacts 足够复盘：prompt、diff、build log、Automation report、verifier result、stdout/stderr。

## 风险与约束

- UE 原生 Automation report 的 JSON 字段可能随版本变化，verifier 应把解析逻辑封装成宽容读取，但不能把测试失败误判为通过。
- PIE、World、Actor lifecycle 类测试更慢且更易受环境影响，本组三任务默认使用 `-nullrhi` 和 non-PIE headless；后续可单独设计 PIE benchmark。
- 性能测试只能验证 scope 排除能力，不应把运行耗时作为稳定评分核心。
- 为避免污染基线项目，setup 只改 trial workspace，所有生成报告只写入 workspace 的 `Saved/Automation/` 和 benchmark artifacts。

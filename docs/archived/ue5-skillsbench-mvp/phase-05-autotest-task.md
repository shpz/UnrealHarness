# Phase 05 - Automation Test Task

## 目标

实现 `tps-autotest-add-character-tests`，用于评估 agent 是否能借助 `ue-autotest` 和 `ue-build` 为 UE5 C++ 项目创建、注册并运行 Automation Test。

## 前置条件

- Phase 04 已完成。
- runner 能注入 `ue-autotest`、`ue-build`。
- verifier 能调用 `UnrealEditor-Cmd.exe` 并收集 Automation 报告。

## 执行与审核

- 执行 subagent：负责实现 `tps-autotest-add-character-tests` 的 helper fixture、测试模块要求、oracle patch 和 Automation verifier；不得扩展到 PIE、World、Actor lifecycle 或性能测试。
- subagent 交回内容：setup 后 oracle 前的失败证据、应用 oracle 后的通过证据、连续 3 次 oracle 运行结果、Automation report artifacts、测试数不足或未注册模块的 verifier 拒绝证据。
- 主 agent 审核重点：测试模块注册路径完整、至少 3 个目标 scope 测试真实运行并通过、verifier 能识别跳过/失败/数量不足、artifacts 可追溯。

## 交付物

- `benchmarks/ue5-skillsbench/tasks/tps-autotest-add-character-tests/instruction.md`
- `benchmarks/ue5-skillsbench/tasks/tps-autotest-add-character-tests/task.toml`
- `benchmarks/ue5-skillsbench/tasks/tps-autotest-add-character-tests/setup.ps1`
- `benchmarks/ue5-skillsbench/tasks/tps-autotest-add-character-tests/oracle.patch`
- `benchmarks/ue5-skillsbench/tasks/tps-autotest-add-character-tests/verifier.ps1`

## 任务设计

当前 `sample/TPSample` 没有测试模块。因此 fixture 应提供一个适合无头测试的纯 C++ helper，然后要求 agent 创建并注册 `TPSampleTest` Editor 模块。

建议 setup 注入：

- `Source/TPSample/Public/TPSampleInputMath.h`
- `Source/TPSample/Private/TPSampleInputMath.cpp`

helper 应具备：

- 纯数据输入输出。
- 不依赖 World、Actor lifecycle、viewport 或真实渲染。
- 可覆盖 happy path、edge、regression 三类场景。

`instruction.md` 只描述：

- 为指定 helper 新增 UE Automation tests。
- 至少包含 happy path、edge、regression 三个测试。
- 创建必要的 Editor test module 并完成注册。
- 使用 headless Automation 运行通过。

不在 instruction 中提到 `ue-autotest`。

## Verifier

`verifier.ps1` 执行：

1. 检查 `Source/TPSampleTest/TPSampleTest.Build.cs` 存在。
2. 检查 `.uproject` 中注册 `TPSampleTest`，且模块类型为 `Editor`。
3. 检查 `Source/TPSampleEditor.Target.cs` 的 `ExtraModuleNames` 包含 `TPSampleTest`。
4. 构建 `TPSampleEditor Win64 Development`。
5. 使用 `UnrealEditor-Cmd.exe` 运行指定 Automation scope，例如 `TPSample.Input.*`。
6. 解析 UE 原生 `index.json` 或 `Saved/Automation/autotest_results.json`。
7. 要求目标 scope 下至少 3 个测试。
8. 要求目标测试全部 pass。

## Oracle 要求

`oracle.patch` 应展示推荐实现：

- 新增 `TPSampleTest` Editor module。
- `TPSampleTest.Build.cs` 只添加必要依赖。
- `.uproject` 注册测试模块。
- `TPSampleEditor.Target.cs` 添加测试模块。
- 新增 `Private/TPSampleInputMathTest.cpp`。
- 测试命名遵循 `TPSample.Input.<Feature>.<Scenario>`。
- 使用 `IMPLEMENT_SIMPLE_AUTOMATION_TEST`。
- 默认使用 `ApplicationContextMask | EngineFilter`。

## 验收标准

- setup 后、oracle 前，verifier 必须失败。
- 应用 `oracle.patch` 后，verifier 必须通过。
- oracle 连续运行 3 次均通过。
- verifier 能识别没有注册测试模块、测试数不足、测试被跳过、测试失败等情况。
- Automation artifacts 被复制到 trial artifacts 目录。

## 暂不处理

- 不做 PIE、World、Actor lifecycle 测试。
- 不要求 `-NoNullRHI`。
- 不做性能测试。
- 不实现 `tps-autotest-fix-failing-test`，该任务放到 MVP 后扩展。

## 风险

- Automation report 在不同 UE 小版本中的 JSON 字段可能不同。verifier 应优先解析原生 report，失败时回退解析日志，并把解析失败归类为 `verifier-error` 或 `test`。

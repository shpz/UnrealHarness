# Phase 03 - Build Repair Task

## 目标

实现第一个正式任务 `tps-build-module-dependency-repair`，用于评估 agent 在 UE C++ 构建失败时是否能借助 `ue-build` 和可选 `ue-lsp` 更稳定地定位并修复模块依赖或 include 问题。

## 前置条件

- Phase 02 smoke task 已通过。
- UBT verifier 可稳定构建 clean `TPSampleEditor`。
- oracle adapter 可应用 patch 并收集 diff。

## 执行与审核

- 执行 subagent：负责实现 `tps-build-module-dependency-repair` 的 fixture、instruction、metadata、oracle patch 和 verifier；不得要求真实 agent 通过或加入 ablation。
- subagent 交回内容：setup 后 oracle 前的失败证据、应用 oracle 后的通过证据、连续 3 次 oracle 运行结果、删除 fixture 绕过修复的 verifier 拒绝证据。
- 主 agent 审核重点：instruction 未泄漏 skill 名称或答案、fixture 需要真实 UE 构建知识、oracle patch 是最小修复、verifier 能区分正确修复和绕过。

## 交付物

- `benchmarks/ue5-skillsbench/tasks/tps-build-module-dependency-repair/instruction.md`
- `benchmarks/ue5-skillsbench/tasks/tps-build-module-dependency-repair/task.toml`
- `benchmarks/ue5-skillsbench/tasks/tps-build-module-dependency-repair/setup.ps1`
- `benchmarks/ue5-skillsbench/tasks/tps-build-module-dependency-repair/oracle.patch`
- `benchmarks/ue5-skillsbench/tasks/tps-build-module-dependency-repair/verifier.ps1`

## 任务设计

Fixture 应制造一个明确、可复现、需要 UE 构建知识处理的问题：

- 方案 A：从 `TPSample.Build.cs` 移除一个源码实际依赖的模块。
- 方案 B：新增一个小型源码文件，引用某个 UE 模块 API，但故意不添加对应 dependency。

优先选择方案 B。原因是它能把错误控制在 task fixture 中，减少对模板项目原始代码的耦合。

`instruction.md` 只描述目标：

- 当前 UE5 项目无法构建。
- 请修复构建失败。
- 不要删除功能代码或绕过被测逻辑。
- 成功标准是 `TPSampleEditor Win64 Development` 构建通过。

不在 instruction 中提到具体 skill 名称。

## Verifier

`verifier.ps1` 执行：

1. 运行 UBT 构建 `TPSampleEditor Win64 Development`。
2. 检查 exit code 为 0。
3. 检查 build log 不包含：
   - `error C`
   - `fatal error`
   - `UnrealHeaderTool failed`
   - `error LNK`
4. 静态检查被测 fixture 文件仍存在。
5. 静态检查关键功能代码没有被删除。

## 验收标准

- setup 后、oracle 前，verifier 必须失败。
- 应用 `oracle.patch` 后，verifier 必须通过。
- oracle 连续运行 3 次均通过。
- verifier 能识别通过删除 fixture 文件绕过任务的错误修复。
- `task.toml` metadata 使用 `software-engineering`、`build-repair`、`compiler-toolchain`、`unreal-engine` 等标签。

## 暂不处理

- 不要求真实 agent 在本阶段通过。
- 不做 ablation。
- 不评估 LSP 实际调用轨迹。

## 风险

- 模块依赖错误可能在不同 UE 版本下表现为不同编译错误。fixture 应尽量使用 UE 5.7 下稳定存在的模块和头文件。

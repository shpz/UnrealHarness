# Phase 04 - LSP API Task

## 目标

实现 `tps-lsp-api-signature-repair`，用于评估 agent 在 UE C++ API 调用、类型或签名错误场景下是否能借助 `ue-lsp` 的工作流说明更稳定地完成定位和修复。

## 前置条件

- Phase 03 的 build repair task 已通过 oracle 验证。
- runner 已支持 skills 条件注入。
- UBT verifier 可作为最终正确性判定。

## 执行与审核

- 执行 subagent：负责实现 `tps-lsp-api-signature-repair` 的 API/签名 fixture、oracle patch 和 verifier；不得把 clangd/LSP 状态脚本作为通过条件。
- subagent 交回内容：setup 后 oracle 前的失败证据、应用 oracle 后的通过证据、连续 3 次 oracle 运行结果、删除 helper 或绕过目标 API 的 verifier 拒绝证据。
- 主 agent 审核重点：instruction 未要求使用 LSP、fixture 确实需要确认 UE API/类型事实、UBT 与静态检查共同判定最终正确性、telemetry 只作为辅助字段。

## 交付物

- `benchmarks/ue5-skillsbench/tasks/tps-lsp-api-signature-repair/instruction.md`
- `benchmarks/ue5-skillsbench/tasks/tps-lsp-api-signature-repair/task.toml`
- `benchmarks/ue5-skillsbench/tasks/tps-lsp-api-signature-repair/setup.ps1`
- `benchmarks/ue5-skillsbench/tasks/tps-lsp-api-signature-repair/oracle.patch`
- `benchmarks/ue5-skillsbench/tasks/tps-lsp-api-signature-repair/verifier.ps1`

## 任务设计

Fixture 注入一个需要确认 UE C++ API 签名或类型事实的错误。候选方式：

- 修改 `TPSampleCharacter.cpp` 中 Enhanced Input 相关调用，使其使用错误参数类型或错误 overload。
- 新增一个小型 helper，调用 UE API 时使用过期或错误签名。
- 新增一处 include 或 forward declaration 误用，必须结合真实类型定义修复。

优先选择对 `TPSample` 原有玩法行为影响小的 helper 型 fixture，避免 agent 通过大范围重写输入系统解决。

`instruction.md` 只描述：

- 项目存在一个 UE C++ API 使用错误。
- 请确认正确签名并做最小修复。
- 保留原有功能意图。
- 成功标准是 Editor target 构建通过。

不在 instruction 中要求使用 LSP。

## Verifier

`verifier.ps1` 执行：

1. 运行 UBT 构建。
2. 检查 exit code 为 0。
3. 静态检查 fixture 中的错误调用文本不再出现。
4. 静态检查目标方法、类或 helper 仍存在。
5. 可选：检查修复后的调用使用预期 API 或类型。

## `ue-lsp` 处理方式

当前 `skills/ue-lsp` 没有可执行的 `scripts/status.ps1`。因此 Phase 04 不把 LSP 状态脚本作为 verifier 依赖。

本阶段的评估方式：

- `ue-lsp` 作为 skills 条件中的说明性能力注入。
- 最终结果仍由 UBT 和静态检查判定。
- skill usage telemetry 记录为辅助字段。
- 对 Codex 类 harness，`skill_usage_confidence` 默认不高于 `partial`。

后续增强项：

- 补齐 `skills/ue-lsp/scripts/status.ps1`
- 生成并定位 `compile_commands.json`
- 捕获 clangd diagnostics 作为 artifacts

## 验收标准

- setup 后、oracle 前，verifier 必须失败。
- 应用 `oracle.patch` 后，verifier 必须通过。
- oracle 连续运行 3 次均通过。
- verifier 能识别删除 fixture 或绕过目标 API 的错误修复。
- 任务 metadata 标明 `primary_skills = ["ue-lsp"]`，`secondary_skills = ["ue-build"]`。

## 暂不处理

- 不强制运行 clangd。
- 不要求 telemetry 精确证明 agent 调用了 LSP。
- 不处理 Blueprint 或 generated asset 查询。

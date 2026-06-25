# UE5 SkillsBench MVP 计划

日期：2026-06-12

本计划基于 [`../ue5_skillsbench_design.md`](../ue5_skillsbench_design.md)，目标是在本地 Windows + PowerShell + UE5 环境中先跑通一个私有 SkillsBench-compatible MVP，用 `sample/TPSample` 对 `ue-build`、`ue-lsp`、`ue-autotest` 三个 skill 做可复现基准测试。

## MVP 定义

MVP 完成时应具备：

- 固定使用 `sample/TPSample` 作为只读基线项目。
- 每个 trial 在 `.bench/runs/` 下创建隔离副本。
- 支持 `no-skills` 和 `all-ue-skills` 两个基础条件。
- 至少包含 3 个正式任务：build repair、LSP/API repair、automation test add。
- 每个正式任务有 `setup.ps1`、`oracle.patch`、`verifier.ps1`。
- 每个 verifier 只看最终结果，不读取 skill 目录。
- 至少一个 agent/harness 跑完 3 个任务 x 2 个条件 x 3 次 trial。
- 生成结构化 JSON 和汇总 Markdown 报告。

## 执行与审核模型

- 每个 Phase 由一个独立 subagent 执行，subagent 只负责当前阶段文档列出的交付物、工作项和验收标准。
- 主 agent 负责阶段边界、依赖顺序和最终审核，不直接把多个阶段的实现混在同一个执行上下文里完成。
- subagent 完成阶段后必须向主 agent 提供：变更摘要、执行过的验证命令、失败或跳过的验证项、遗留风险。
- 主 agent 审核时必须对照当前 Phase 的验收标准检查 diff、运行产物和命令结果；审核未通过时，将明确返工项交回当前阶段 subagent 或启动新的同阶段 subagent。
- 除非主 agent 明确批准，subagent 不推进后续 Phase，不修改 `sample/TPSample` 基线项目，不放宽 verifier 或 oracle 要求。

## 阶段拆分

| 阶段 | 文档 | 目标 |
| --- | --- | --- |
| 01 | [`phase-01-harness-foundation.md`](./phase-01-harness-foundation.md) | 搭建 benchmark 目录、runner 骨架、项目复制和安全边界 |
| 02 | [`phase-02-smoke-and-oracle.md`](./phase-02-smoke-and-oracle.md) | 跑通环境 smoke task、oracle adapter 和基础 verifier |
| 03 | [`phase-03-build-repair-task.md`](./phase-03-build-repair-task.md) | 实现第一个正式构建修复任务 |
| 04 | [`phase-04-lsp-api-task.md`](./phase-04-lsp-api-task.md) | 实现 UE C++ API/签名修复任务，间接评估 `ue-lsp` |
| 05 | [`phase-05-autotest-task.md`](./phase-05-autotest-task.md) | 实现 UE Automation Test 新增任务 |
| 06 | [`phase-06-agent-eval-reporting.md`](./phase-06-agent-eval-reporting.md) | 接入 agent adapter，执行矩阵并生成报告 |

## 跨阶段原则

- 不直接修改 `sample/TPSample`。
- 不把 `skills/` 泄漏到 `no-skills` workspace。
- 不把 verifier 逻辑写进 skill 或 agent prompt。
- 不清理 Engine 安装目录、全局 DDC 或仓库根目录。
- 每个阶段先保证 oracle 可 100% 通过，再接入真实 agent。
- 所有运行产物只写入 `.bench/`。

## 推荐完成顺序

按阶段顺序执行。Phase 03、04、05 都依赖 Phase 01 和 Phase 02 的 runner/oracle/verifier 基础设施；Phase 06 依赖三个正式任务都能被 oracle 稳定解出。

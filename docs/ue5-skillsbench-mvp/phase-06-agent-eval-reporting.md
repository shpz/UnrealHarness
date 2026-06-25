# Phase 06 - Agent Eval And Reporting

## 目标

接入真实 agent/harness，执行 MVP 评测矩阵，并生成结构化结果和汇总报告。这个阶段开始真正回答 skills 是否提升 UE5 工作流成功率。

## 前置条件

- Phase 03、04、05 的正式任务均已实现。
- 每个正式任务 oracle 连续 3 次通过。
- `no-skills` workspace 不包含 skill 内容。
- `all-ue-skills` workspace 只包含允许注入的 skill。

## 执行与审核

- 执行 subagent：负责实现 agent adapter、18 个 MVP trial 的执行矩阵、artifact 收集和报告聚合；不得发布 leaderboard、接入上游 BenchFlow/Harbor 或把耗时作为主排名指标。
- subagent 交回内容：完整 18 trial 结果目录、汇总 JSON、汇总 Markdown、失败分类说明、`sample/TPSample` 未修改的证据。
- 主 agent 审核重点：`no-skills` 与 `all-ue-skills` 隔离正确、每个 trial 都有 `result.json` 和 artifacts、pass rate/delta_pp/normalized_gain 可复算、失败 trial 可追溯到 workspace/diff/log。

## 交付物

- `benchmarks/ue5-skillsbench/runner/adapters/codex.ps1`
- 可选：`claude-code.ps1`、`opencode.ps1`
- `benchmarks/ue5-skillsbench/runner/lib/Report.ps1`
- `benchmarks/ue5-skillsbench/reports/<run-id>-summary.md`
- `benchmarks/ue5-skillsbench/reports/<run-id>-results.json`

## 评测矩阵

MVP 必跑矩阵：

```text
tasks:
  - tps-build-module-dependency-repair
  - tps-lsp-api-signature-repair
  - tps-autotest-add-character-tests

conditions:
  - no-skills
  - all-ue-skills

trials:
  - 3 per task per condition
```

最小总 trial 数：

```text
3 tasks x 2 conditions x 3 trials = 18 trials
```

MVP 后可选 ablation：

- `build-only`
- `build-lsp`
- `build-autotest`

## 工作项

1. 实现 agent adapter 统一接口：
   - `WorkspaceRoot`
   - `InstructionPath`
   - `SkillsRoot`
   - `Condition`
   - `TimeoutMinutes`
   - `ArtifactsDir`
2. 实现 `codex` adapter：
   - 在 workspace 内执行任务。
   - 按 condition 注入或不注入 skill 内容。
   - 记录 skill invocation surface 和 confidence。
3. 完善 skill injection：
   - `no-skills` 不复制 `skills/`。
   - `all-ue-skills` 复制 `ue-build`、`ue-lsp`、`ue-autotest`。
   - 不复制 oracle、verifier 或 task 内部答案。
4. 每个 trial 后收集：
   - git diff
   - agent stdout/stderr
   - verifier stdout/stderr
   - build log
   - automation report
   - `result.json`
5. 实现 report 聚合：
   - pass rate
   - delta_pp
   - normalized_gain
   - mean wall clock seconds
   - failure class distribution
   - per-task/per-condition table
6. 标记 telemetry 可信度：
   - Codex 默认 `skill_usage_confidence = "partial"`
   - 显式 tool-call harness 才可标为 `high`

## 验收标准

- 完成 18 个 MVP trial。
- 每个 trial 都生成 `result.json` 和 artifacts。
- 汇总 JSON 可机器读取。
- 汇总 Markdown 可人工阅读。
- 报告包含每个 task 在 `no-skills` 与 `all-ue-skills` 下的 pass rate。
- 报告包含 `delta_pp` 和 `normalized_gain`。
- 失败 trial 可追溯到 workspace、diff、agent log、verifier log。
- `sample/TPSample` 在整轮评测后保持未修改。

## 暂不处理

- 不发布公开 leaderboard。
- 不接入上游 BenchFlow/Harbor。
- 不做跨机器统计。
- 不把耗时作为主排名指标。

## 风险

- agent adapter 可能受本地 CLI 能力限制。若 Codex 无法原生加载 skill path，先记录为 prompt-fragment 注入，并在报告中明确 `skill_invocation_surface`。
- 部分失败可能来自 UE 环境或缓存状态。所有环境类失败必须归类为 `environment`，不混入 agent 能力失败。

# UE5 SkillsBench 调研

调研日期：2026-06-11

## 结论

SkillsBench 是 BenchFlow 团队维护的 agent skills 基准框架，目标是评估“可复用的 Skills 是否真的提升 agent 完成任务的能力”。它不是单纯测模型能力，而是比较同一任务在无 skills、有人工 curated skills、以及自生成 skills 等条件下的通过率差异。

对本仓库的意义：`ue-build`、`ue-lsp`、`ue-autotest` 这类 UE5 workflow skills 可以按 SkillsBench 的任务格式做成一组可复现任务，用同一批 agent/model 在“无 UE skills”和“注入 UE skills”两种条件下跑，量化 pass rate delta 和 normalized gain。

直接接入上游 SkillsBench 有一个现实限制：SkillsBench 当前任务默认是 Harbor/BenchFlow 风格的容器化任务，而本仓库 UE skills 明确依赖 Windows、PowerShell、已安装 Unreal Engine。UE5 Editor/UBT 的体积、Epic 授权、Windows/Linux runner 差异都会影响公开复现。因此更稳妥的路线是先做一个私有 UE5 SkillsBench-compatible harness，跑通指标和任务设计后，再评估是否贡献到上游或做成独立 benchmark。

## 资料来源

- GitHub: https://github.com/benchflow-ai/skillsbench
- Website / leaderboard: https://www.skillsbench.ai
- Paper: https://arxiv.org/abs/2602.12670
- Dataset: https://huggingface.co/datasets/benchflow/skillsbench
- BenchFlow SDK: https://github.com/benchflow-ai/benchflow

## SkillsBench 是什么

上游 README 定义：SkillsBench measures how effectively agents leverage skills, 即评估 agent 使用“由说明、脚本、参考资料组成的模块化 skill 文件夹”完成专业工作流的效果。

核心目标：

- 建立覆盖多领域的 agent skills benchmark。
- 设计需要 2 个以上 skills 组合的真实任务。
- 比较不同模型、agent harness 和 skill 配置下的表现。
- 用 deterministic verifier 评估最终结果，而不是评估 agent 是否照着某个步骤做。

论文 v3 摘要里的关键结果：

- 论文快照包含 86 个任务、11 个领域、curated skills 和 deterministic verifiers。
- 每个任务比较 no skills、curated skills、self-generated skills 三种条件。
- Curated skills 平均提升 16.2 个百分点。
- 不同领域差异明显：Software Engineering 约 +4.5pp，Healthcare 约 +51.9pp。
- 有 16/84 个任务出现 negative deltas，说明 skills 可能帮倒忙。
- Self-generated skills 平均没有收益，说明模型还不能稳定产出自己后续受益的程序性知识。

网站当前 leaderboard 已更新到另一批数据：94 tasks、最多 3 trials per task、16 个 agent-model configurations。leaderboard 代码给出的 normalized gain 公式是：

```text
g = (pass_skill - pass_vanilla) / (1 - pass_vanilla)
```

## 任务格式

SkillsBench 使用 Harbor task format。一个任务目录通常长这样：

```text
tasks/<task-id>/
├── instruction.md
├── task.toml
├── environment/
│   ├── Dockerfile
│   └── skills/
│       └── <skill-name>/
│           ├── SKILL.md
│           ├── scripts/
│           └── references/
├── solution/
│   └── solve.sh
└── tests/
    ├── test.sh
    └── test_outputs.py
```

重要规则：

- `instruction.md` 只描述任务目标和成功标准，不要告诉 agent 用哪个 skill。
- verifier 必须 outcome-based，例如检查文件、构建结果、测试结果、性能阈值。
- skills 不要 bake 进 Docker image，否则无 skills baseline 会被污染。
- 有 skills 条件通过 `-s tasks/<task-id>/environment/skills/` 注入。
- oracle solution 必须能 100% 通过 verifier。
- 任务最好自包含、依赖固定、无需外部 API key。

常用命令：

```bash
uv sync --locked
uv run bench tasks init <task-name>
uv run bench tasks check tasks/<task-id>
uv run bench eval create -t tasks/<task-id> -a oracle

# 有 skills
uv run bench eval create -t tasks/<task-id> -a claude-agent-acp -m <model> \
  -s tasks/<task-id>/environment/skills/

# 无 skills
uv run bench eval create -t tasks/<task-id> -a claude-agent-acp -m <model>

# 跨任务评估单个 skill
uv run bench skills eval tasks/<task-id>/environment/skills/<skill-name>/ -a claude-agent-acp
```

## 元数据和分类

上游正在把任务标签收敛到受控 taxonomy。建议 UE5 任务直接采用当前 schema：

```toml
[metadata]
difficulty = "medium"
category = "software-engineering"
subcategory = "build-repair"
category_confidence = "high"
task_type = ["repair", "debugging"]
modality = ["source-code"]
interface = ["terminal", "compiler-toolchain"]
skill_type = ["debugging-heuristic", "tool-workflow"]
tags = ["unreal-engine", "ue5", "ubt", "uht"]
```

UE5 相关任务大多应归入：

- `category = "software-engineering"`：构建修复、API 迁移、测试编写、模块依赖修复。
- `interface = ["terminal", "compiler-toolchain"]`：UBT/UHT/UAT/UnrealEditor-Cmd。
- `skill_type` 可按任务选择 `tool-workflow`、`debugging-heuristic`、`library-api-usage`、`evaluation-protocol`。

## Harness 差异

上游 `docs/harnesses/skill-invocation-surfaces.md` 对多个 harness 的 skill 加载方式做了源码级审计。

和本仓库最相关的点：

- Claude Code、OpenCode、OpenHands 把 skill 作为显式 tool 调用，trajectory 中比较容易统计 skill usage。
- Codex 不是 tool call，而是把 `<skill>` 内容作为 user-role prompt fragment 注入；显式 `$skill-name` 和部分命令模式会触发注入。
- Codex trajectory 里不一定完整记录隐式 skill invocation，精确统计需要额外 telemetry 或日志。
- Codex/OpenHands 主要识别 `name` 和 `description`；`allowed-tools` 这类 frontmatter 在多个 harness 中不一定生效。

对 UE5 benchmark 的影响：

- pass/fail 指标应该以 verifier 为准，skill usage 只做辅助分析。
- 如果比较不同 harness，必须记录每个 harness 的 skill discovery path 和 invocation surface。
- 对 Codex 要把“是否使用 skill”的分析标成 partial confidence，不能只按 tool calls 统计。

## UE5 适配风险

SkillsBench 的默认可复现模型和 UE5 的工程现实不完全匹配：

- UE5 Editor/Engine 体积巨大，公开 Docker image 成本高。
- Epic 授权不适合把完整 Engine 直接随公开 benchmark 分发。
- 当前仓库 skills 偏 Windows + PowerShell；上游 SkillsBench 默认任务更接近 Linux container。
- UE5 headless 测试可用 `UnrealEditor-Cmd.exe -nullrhi`，但渲染、PIE、资源加载类任务可能需要 `-NoNullRHI` 或真实 GPU/GUI。
- UBT/UHT/DerivedDataCache 会带来冷启动时间和环境噪声，评测要区分 agent 质量和机器缓存状态。

建议优先做两阶段：

1. 私有本地 benchmark：固定 Windows runner、UE 5.x 版本、PowerShell、引擎路径和样例项目，先验证 skills 是否带来稳定增益。
2. Harbor-compatible 任务：如果要对齐上游，提供可复制的 task layout、verifier、metadata；Engine image 或安装步骤放到私有 runner/CI，不把 Engine bake 到公开仓库。

## 建议的 UE5 任务集

第一批任务控制在 6-9 个，覆盖本仓库三个 skills，避免任务过大。

### 1. `ue-build-module-dependency-repair`

目标：给一个 UE C++ 项目，源码中使用了某个模块 API，但 `.Build.cs` 缺少依赖或 include 错误。agent 需要修复构建。

Skills：`ue-build` + `ue-lsp`

Verifier：

- 运行 UBT Development Editor build。
- 检查 exit code 为 0。
- 检查日志中无 `error C`、`fatal error`、`UnrealHeaderTool failed`。

### 2. `ue-uht-reflection-repair`

目标：项目中存在 `UCLASS`、`UPROPERTY`、`.generated.h`、specifier 顺序或 module export 相关错误。agent 需要修复 UHT/反射问题。

Skills：`ue-build` + `ue-lsp`

Verifier：

- 运行 UBT，确保 UHT 阶段通过。
- 可加入一个最小 automation test 验证反射字段可访问。

### 3. `ue-automation-test-add`

目标：给一个已有 C++ gameplay/helper API，要求新增 UE Automation Test，覆盖 happy path、edge、regression 三类场景。

Skills：`ue-build` + `ue-autotest`

Verifier：

- 构建 Editor target。
- 用 `UnrealEditor-Cmd.exe` headless 运行指定 automation scope。
- 解析 JSON report，要求新增测试数量和全部 pass。

### 4. `ue-automation-test-fix`

目标：给一个已失败的 automation test suite，agent 需要判断是测试代码问题还是生产代码问题，并做最小修复。

Skills：`ue-build` + `ue-autotest`

Verifier：

- 运行同一 automation scope。
- 检查失败用例归零。
- 检查没有删除目标测试、没有降低断言强度。

### 5. `ue-api-migration`

目标：给一个使用旧 UE API 或错误 overload 的 C++ 文件，agent 需要通过符号定义、签名和引用完成迁移。

Skills：`ue-lsp` + `ue-build`

Verifier：

- 生成或提供 `compile_commands.json`。
- 构建通过。
- 可静态检查目标旧 API 不再出现。

### 6. `ue-packaging-log-triage`

目标：给一段 UAT packaging 失败日志和项目配置，agent 需要定位根因并修复配置或代码。

Skills：`ue-build`

Verifier：

- 运行简化 package/cook 命令或一个可替代的 deterministic check。
- 检查最终产物或日志成功标记。

## 评测设计

最小矩阵：

```text
tasks: 6-9 UE5 tasks
conditions:
  - no skills
  - current UE skills
  - ablation: only ue-build / only ue-lsp / only ue-autotest where applicable
trials: 每 task 每 condition 至少 3 次
agents:
  - Codex
  - Claude Code
  - OpenCode
  - Kimi Code 或其他本仓库支持的 skill-enabled agent
metrics:
  - pass rate
  - delta in percentage points
  - normalized gain g
  - mean wall-clock time
  - failure class: build, UHT, test, timeout, wrong fix, environment
```

判定要点：

- 主指标用 verifier pass/fail。
- 负增益同样要记录，不能只报告成功样例。
- 对同一任务固定 UE 版本、初始项目、缓存策略和超时。
- 不要把 skill 内容、oracle 或 verifier 细节暴露给无 skills baseline。

## 本仓库后续工作

建议下一步按这个顺序推进：

1. 增加 `benchmarks/ue5-skillsbench/` 或 `tasks/` 目录，先放 1 个最小任务样例。
2. 抽象一个本地 runner：准备项目副本、注入/不注入 skills、运行 agent、执行 verifier。
3. 把 `ue-build`、`ue-lsp`、`ue-autotest` 复制或链接到任务的 `environment/skills/`，确保 no-skills 条件不泄漏。
4. 为第一个任务写 oracle 和 verifier，先保证 oracle 100% 通过。
5. 跑 no-skills vs current-skills 各 3 次，生成一份本地报告。
6. 根据失败轨迹修订 skill 描述和任务设计，再扩展到完整任务集。

## 初步判断

SkillsBench 的方法论非常适合衡量本仓库的价值，因为它直接回答“这些 UE skills 是否让 agent 更稳定地完成 UE 工作流”。但 UE5 的运行环境不适合一开始就追求完全上游兼容。工程上应先做本地私有基准，把任务、verifier 和指标稳定下来，再决定是否做公开 Harbor/BenchFlow 版本。

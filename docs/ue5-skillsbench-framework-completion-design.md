# UE5 SkillsBench 框架补全设计

日期：2026-07-02

本文定义当前 `ue5-skillsbench` 框架在不兼容原版 BenchFlow/SkillsBench 的前提下，还需要补齐哪些能力，才能成为一个可复现、可解释、面向 UE5 场景的 skills benchmark。

相关文档：

- [`ue-autotest-benchmark-tasks-design.md`](./ue-autotest-benchmark-tasks-design.md)：`ue-autotest` 三套任务设计。
- [`ue5-skillsbench-mvp/README.md`](./ue5-skillsbench-mvp/README.md)：历史 MVP 计划，已过时，仅作为早期背景参考。

## 目标与非目标

### 目标

框架目标是回答以下问题：

1. UE5 专用 skill 是否能提升 agent 在真实 UE5 工作流中的成功率。
2. 提升来自哪里：构建定位、Automation 运行、报告解析、scope 控制、修复闭环，还是减少无效尝试。
3. 不同 skill 条件之间是否存在增益、冗余或干扰。
4. 失败模式是否能被稳定分类并复盘。

MVP 完成时，应能稳定运行：

- build 类任务：评估 `ue-build`。
- automation 类任务：评估 `ue-autotest` 与 `ue-build` 组合。
- 至少一个真实 agent 在多条件、多 trial 下生成可对比报告。

### 非目标

本框架不追求：

- 兼容原版 BenchFlow native `task.md` 包格式。
- 使用 Docker sandbox 运行 UE5 任务。
- 接入原版 SkillsBench registry、Hugging Face dataset 或 public leaderboard。
- 在 MVP 阶段纳入 `ue-lsp`。

UE5 benchmark 允许使用 Windows、本机 Unreal Engine、隔离 workspace 和自研 Python runner。论文方法论中应保留的是对照实验、oracle、deterministic verifier、skill impact 指标和 trajectory 复盘，而不是原版工程载体。

## 当前状态快照

当前已有能力：

- `benchmark.yaml` 声明基线项目、skill、conditions、trial 数和 artifacts。
- Python runner 支持 `preflight`、`run-single`、`run-matrix`、`report`。
- 每个 trial 会复制 `sample/TPSample` 到隔离 workspace。
- condition 能控制 skill 注入，当前有 `no-skills` 与 `ue-build-only`。
- adapter 支持 `oracle`、`noop`、`manual`、`codex`、`kimi-code`。
- task 目录支持 `task.toml`、`instruction.md`、`setup.py`、`verifier.py`。
- report 能汇总 pass rate、delta percentage points、normalized gain、耗时和 failure class。

当前主要不足：

- 任务只覆盖 `ue-build`，尚未覆盖 `ue-autotest`。
- condition 不能表达 `ue-autotest-with-build`、`all-ue-skills` 等实验矩阵。
- oracle 只有 `oracle.patch` adapter 形状，但当前任务没有稳定 oracle baseline。
- verifier 输出结构还未对 Automation report、scope、报告产物形成统一协议。
- runner 不记录 skill 使用轨迹、命令次数、重试次数、首次有效行动等过程指标。
- README 与历史 MVP 文档仍描述旧命令和旧 PowerShell 方案。
- 缺少 runner 自测和最小真实 agent 跑数记录。

## MVP 判定标准

新的 MVP 不再以历史文档中的 PowerShell 阶段划分为准，而以实验闭环为准。

MVP 必须满足：

1. 至少 6 个任务：3 个 build 任务、3 个 `ue-autotest` 任务。
2. 至少 3 个 conditions：`no-skills`、对应单 skill 条件、组合 skill 条件。
3. 每个任务有可重复 oracle baseline，oracle 连续运行 3 次均通过。
4. 每个任务的 verifier 只验证最终状态和运行产物，不读取 skill 目录。
5. 每个 task 在 oracle 前应处于失败态或缺少必要产物；oracle 后必须通过。
6. 至少完成一次真实 agent 小矩阵：2 个任务 x 2 个 conditions x 2 trials。
7. 报告能展示 skill impact，而不仅是单次成功/失败。
8. artifacts 足够复盘：prompt、diff、stdout/stderr、build log、Automation report、verifier result、runner result。

建议完整 MVP 矩阵：

```text
6 tasks x 3 conditions x 3 trials = 54 runs
```

## 任务模型补全

### 标准任务目录

每个任务目录应统一为：

```text
benchmarks/ue5-skillsbench/tasks/<task-id>/
  task.toml
  instruction.md
  setup.py
  verifier.py
  oracle.patch          # 可选，代码修复类任务使用
  oracle.py             # 可选，运行/报告类任务使用
  fixtures/             # 可选，setup 注入的源码或输入文件
  README.md             # 可选，给 benchmark 维护者阅读，不给 agent
```

其中：

- `instruction.md` 是 agent 唯一看到的任务说明，不直接说“使用某 skill”。
- `setup.py` 只修改 trial workspace，不修改 `sample/TPSample`。
- `verifier.py` 只检查最终项目状态和 artifacts。
- `oracle.patch` 表示最终代码形状。
- `oracle.py` 表示非 patch 型 oracle action，例如运行指定 Automation scope 并生成报告。

### `task.toml` 建议字段

当前字段可继续使用，但需要补充 oracle、verifier 和 expected artifacts 约定：

```toml
id = "tps-autotest-add-input-math-tests"
project = "TPSample"
timeout_minutes = 45
primary_skills = ["ue-autotest"]
secondary_skills = ["ue-build"]

[metadata]
difficulty = "medium"
category = "software-engineering"
subcategory = "automation-test-authoring"
task_type = ["implementation", "verification"]
modality = ["source-code"]
interface = ["terminal", "compiler-toolchain"]
skill_type = ["tool-workflow", "debugging-heuristic"]
tags = ["unreal-engine", "ue5", "automation", "headless"]

[oracle]
type = "patch" # patch | action | none
path = "oracle.patch"
repeat = 3

[verifier]
type = "python"
path = "verifier.py"
timeout_minutes = 45

[artifacts]
required = [
  "verifier_result.json",
  "build.log",
  "automation/index.json",
  "automation/autotest_results.json",
  "automation/report.md",
]
```

这些字段不必一次性全由 runner 强制校验，但文档和 task authoring 应先统一。

## Condition 矩阵补全

`benchmark.yaml` 应从单一 `ue-build` 扩展到 build 与 autotest 组合实验：

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
  - id: ue-autotest-only
    skills: [ue-autotest]
  - id: ue-autotest-with-build
    skills: [ue-build, ue-autotest]
  - id: all-ue-skills
    skills: [ue-build, ue-autotest]
```

MVP 跑数时不要求每个任务都跑所有 conditions。推荐按任务类型选择：

| 任务类型 | 必跑 conditions | 可选 conditions |
| --- | --- | --- |
| build | `no-skills`, `ue-build-only`, `all-ue-skills` | 无 |
| autotest authoring | `no-skills`, `ue-autotest-with-build`, `all-ue-skills` | `ue-autotest-only` |
| autotest repair | `no-skills`, `ue-autotest-with-build`, `all-ue-skills` | `ue-build-only` |
| autotest reporting | `no-skills`, `ue-autotest-with-build` | `ue-autotest-only` |

`all-ue-skills` 目前可等价于 `[ue-build, ue-autotest]`。保留该 condition 名称是为了未来加入更多 UE skill 时不改变历史报告字段。

## Oracle 机制补全

### 为什么仍需要 oracle

不兼容原版不代表可以没有 oracle。oracle 的作用是证明：

- 任务可解。
- verifier 没有误判。
- setup 产生了预期失败态。
- 任务难度来自 UE 工作流，而不是 fixture 损坏或环境漂移。

### Oracle 类型

框架应支持三类 oracle：

1. `patch`：应用 `oracle.patch` 后运行 verifier。适合 build repair、test authoring、bug repair。
2. `action`：执行 `oracle.py` 或 `oracle.ps1` 后运行 verifier。适合 scoped report 这类无代码变更任务。
3. `none`：仅用于 smoke/preflight，不进入正式 skill impact 统计。

### Oracle 验收

每个正式任务必须满足：

```text
setup 后 verifier 失败或缺少必要产物
oracle 后 verifier 通过
oracle 重复 3 次通过
```

runner 应提供独立命令：

```bash
python -m benchmarks.ue5-skillsbench.runner validate-task --task-id <task-id>
python -m benchmarks.ue5-skillsbench.runner validate-oracle --task-id <task-id> --repeat 3
```

如果暂不实现新命令，也应先用 `run-single --adapter oracle` 固化同等流程。

## Verifier 协议补全

### 统一输出结构

所有 verifier 应写出：

```json
{
  "passed": false,
  "failure_class": "automation-discovery",
  "checks": [
    {"name": "build", "passed": true},
    {"name": "automation_scope", "passed": false, "details": "0 tests discovered"}
  ],
  "build": {
    "target": "TPSampleEditor",
    "platform": "Win64",
    "configuration": "Development",
    "duration_seconds": 123.4,
    "log": "build.log"
  },
  "automation": {
    "requested_scopes": ["TPSample.Input.*"],
    "executed_tests": 0,
    "passed_tests": 0,
    "failed_tests": 0,
    "skipped_tests": 0,
    "report_parser": "native-index-json"
  },
  "artifacts": {
    "automation_report": "automation/index.json",
    "markdown_report": "automation/report.md"
  }
}
```

### Failure class

统一 failure class，便于跨任务聚合：

- `setup`：fixture 注入失败。
- `build`：项目或测试模块无法编译。
- `registration`：测试模块未注册或 target 配置错误。
- `automation-discovery`：目标 scope 未发现测试或测试数量不足。
- `test`：Automation 测试失败。
- `reporting`：测试通过但结构化或 Markdown 报告缺失。
- `scope`：运行了错误 scope，例如包含不应运行的 performance tests。
- `cheating`：删除测试、弱化断言、绕过 verifier 目标。
- `agent-crash`：agent adapter 失败。
- `timeout`：agent、build 或 verifier 超时。
- `verifier-error`：verifier 自身异常。

### Automation report 解析

`ue-autotest` 任务 verifier 应将 UE report 解析封装为共享 helper，而不是每个任务复制解析逻辑。

解析优先级：

1. `Saved/Automation/Reports/**/index.json`
2. `Saved/Automation/autotest_results.json`
3. editor log 中的 Automation summary

允许宽容字段读取，但不允许在无法确认测试结果时判定通过。解析路径必须写入 `checks` 或 `automation.report_parser`。

## Runner 需要补齐的能力

### 任务选择

`run-matrix` 当前发现所有 task 后直接跑所有 conditions。需要支持：

```bash
--task-id <id>              # 可重复
--task-filter autotest      # 按 tag/subcategory 过滤
--condition <id>            # 可重复
--trials 3                  # 覆盖 benchmark.yaml 默认值
--run-id <id>
```

否则新增 conditions 后会让每个 task 跑不相关条件，浪费 UE 构建时间。

### Artifact 布局

建议每个 trial 固定产物结构：

```text
artifacts/
  agent.prompt.md
  agent.stdout.log
  agent.stderr.log
  setup.stdout.log
  setup.stderr.log
  verifier.stdout.log
  verifier.stderr.log
  git.diff
  git.filtered.diff
  result.json
  verifier_result.json
  build.log
  automation/
    index.json
    autotest_results.json
    report.md
    editor.log
```

runner 应负责把 workspace 中的 Automation report 复制到 artifacts，避免 trial workspace 被清理后无法复盘。

### Skill 注入校验

runner 应在每次 trial 的 `prompt-input.json` 或 `result.json` 中记录：

- condition id。
- 注入的 skill 名称。
- 注入的 skill 源路径。
- 注入后的 skill 目标路径。
- `no-skills` 条件下确认 skills root 为空或不存在。

这不是评分依据，但能排查实验污染。

### Trajectory 观测

MVP 不要求完整录屏或 token 级 tracing，但应记录可获得的过程指标：

- agent wall-clock seconds。
- build/verifier duration。
- adapter exit code 与 timeout。
- git diff 文件数、增删行。
- 是否产生 Automation report。
- build 或 Automation 命令执行次数，若 adapter 可观测。
- skill 文件访问记录，若具体 agent/harness 能提供。

如果某些 agent 暂时无法记录命令级 telemetry，报告中应显示为 `unknown`，不要伪造。

## Reporting 补全

报告应从“通过率表格”升级为“skill impact 分析”。

### 必需指标

每个 task x condition：

- trials。
- passed。
- pass rate。
- mean / median wall-clock。
- mean build duration。
- mean verifier duration。
- failure class distribution。
- mean files changed / lines changed。

每个 task 的 condition 对比：

- delta percentage points。
- normalized gain。
- speedup / slowdown。
- 是否存在新增 failure class。

每个 skill 的聚合：

- 相关任务 pass-rate gain。
- 非相关任务是否出现负迁移。
- 最常见失败类型。

### 报告输出

建议固定生成：

```text
reports/<run-id>-results.json
reports/<run-id>-summary.md
reports/<run-id>-failures.md
```

其中 `failures.md` 专门列出失败 trial 的：

- task。
- condition。
- trial。
- failure class。
- verifier failed checks。
- artifacts 路径。
- diff 路径。

## 任务集补全计划

### Build 任务

保留现有 build 任务，但应区分 smoke 与正式任务：

| 任务 | 建议处理 |
| --- | --- |
| `tps-build-basic` | 标记为 smoke，不计入正式 skill impact 或单独分组 |
| `tps-build-engine-resolve` | 可保留为正式 `ue-build` 任务 |
| `tps-build-incremental` | 可保留，但需确认它不是纯运行 build，而是能体现 skill 差异 |
| 新 build repair 任务 | 建议新增 module dependency / Build.cs / Target.cs 修复类任务 |

正式 build 任务应优先是 repair 型，而不是单纯“请编译项目”。

### `ue-autotest` 任务

按现有设计文档落地三套任务：

1. `tps-autotest-add-input-math-tests`
2. `tps-autotest-run-scoped-report`
3. `tps-autotest-fix-failing-error-tests`

实现顺序建议：

1. 先做 `run-scoped-report`，因为它不需要代码修改，能最早打通 Automation report 收集和 verifier 解析。
2. 再做 `add-input-math-tests`，验证 test module 创建、注册和 headless 运行。
3. 最后做 `fix-failing-error-tests`，补防作弊和弱化断言检测。

这个顺序与任务设计文档中的“先 authoring”不同，原因是本文从框架补全角度考虑，优先降低 Automation report 管线风险。

## 框架自测补全

应新增最小 Python 测试，不依赖真实 UE：

```text
tests/benchmark_runner/
  test_config.py
  test_task_discovery.py
  test_report.py
  test_verifier_result_schema.py
  test_condition_skill_injection.py
```

最低覆盖：

- `benchmark.yaml` 能解析多 skill、多 condition。
- `discover_tasks` 只发现有 `task.toml` 的目录。
- report 对缺失 metrics、失败 trial、多个 conditions 能稳定聚合。
- verifier result schema 缺字段时能给出明确错误。
- `no-skills` workspace 不包含 skill 注入。

这些测试不证明 UE 行为正确，但能防止 runner 结构回归。

## 文档与命令补全

需要更新或替换以下内容：

- 顶层 README 中 benchmark 运行命令应改为带子命令的实际形式。
- 历史 `ue5-skillsbench-mvp` 文档应标注为 archived/obsolete。
- 新增 task authoring guide，说明如何写 `setup.py`、`verifier.py`、oracle 和 artifacts。
- 新增 runbook：如何跑 preflight、oracle validation、小矩阵、完整矩阵、报告生成。

推荐命令示例：

```bash
python -m benchmarks.ue5-skillsbench.runner preflight
python -m benchmarks.ue5-skillsbench.runner run-single --task-id tps-build-engine-resolve --condition ue-build-only --adapter codex
python -m benchmarks.ue5-skillsbench.runner run-matrix --adapter codex --run-id <run-id>
python -m benchmarks.ue5-skillsbench.runner report --run-id <run-id>
```

## 分阶段实施建议

### Phase A：框架协议固化

- 更新 `benchmark.yaml`，加入 `ue-autotest` 和组合 conditions。
- 定义 verifier result schema。
- 定义 oracle 类型和 task authoring 约定。
- 修正 README 与过时 MVP 文档标记。

验收：现有 build tasks 仍可 discovery，report 不回归。

### Phase B：Automation report 管线

- 实现共享 Automation report parser。
- 实现 artifacts 复制到 `artifacts/automation/`。
- 落地 `tps-autotest-run-scoped-report`。
- oracle action 能生成报告并通过 verifier。

验收：oracle 连续 3 次通过，错误 scope 能被 verifier 拒绝。

### Phase C：Autotest authoring 与 repair

- 落地 `tps-autotest-add-input-math-tests`。
- 落地 `tps-autotest-fix-failing-error-tests`。
- 补防作弊检查：删除测试、弱化断言、跳过目标 scope。

验收：三个 `ue-autotest` 任务 oracle 均连续 3 次通过。

### Phase D：实验矩阵与报告

- 增加 task/condition filter。
- 报告新增 failure detail 与 skill impact 聚合。
- 跑 2 tasks x 2 conditions x 2 trials 的真实 agent smoke matrix。

验收：报告能清楚比较 `no-skills` 与 skill condition 的差异，并能复盘每个失败 trial。

### Phase E：Runner 自测

- 新增不依赖 UE 的 runner 单元测试。
- 在本地 CI 或手动命令中固定执行。

验收：配置解析、task discovery、report aggregation、schema 校验都有测试覆盖。

## 完成定义

框架补全完成时，应满足：

- `ue-build` 与 `ue-autotest` 都有正式任务覆盖。
- 每个正式任务有 oracle baseline。
- 每个正式任务有 deterministic verifier。
- `no-skills`、单 skill、组合 skill 至少能形成一组可比较结果。
- report 能展示 pass rate、normalized gain、耗时、失败分布和失败复盘入口。
- artifacts 能独立支持人工复盘。
- 文档不再把读者引向过时 PowerShell MVP 或原版 BenchFlow 兼容目标。

达到以上标准后，当前项目可以称为“UE5 场景迁移版 SkillsBench MVP”。在此之前，它更准确地说是 `ue-build` benchmark runner 原型。

# UE5 SkillsBench 框架补全设计 Spec

日期：2026-07-04

状态：设计稿（待实现）

## 1. Overview & Goals

`ue5-skillsbench` 是面向 UE5 真实开发场景的 skills benchmark。它与原版 BenchFlow/SkillsBench 不兼容，目标是回答以下问题：

1. UE5 专用 skill 是否能提升 agent 在真实 UE5 工作流中的成功率。
2. 提升来自哪里：构建定位、Automation 运行、报告解析、scope 控制、修复闭环，还是减少无效尝试。
3. 不同 skill 条件之间是否存在增益、冗余或干扰。
4. 失败模式是否能被稳定分类并复盘。

MVP 完成时，应能稳定运行：

- build 类任务：评估 `ue-build`。
- automation 类任务：评估 `ue-autotest` 与 `ue-build` 组合。
- 至少一个真实 agent 在多条件、多 trial 下生成可对比报告。

## 2. Non-Goals

本框架不追求：

- 兼容原版 BenchFlow native `task.md` 包格式。
- 使用 Docker sandbox 运行 UE5 任务。
- 接入原版 SkillsBench registry、Hugging Face dataset 或 public leaderboard。
- 在 MVP 阶段纳入 `ue-lsp`。

UE5 benchmark 允许使用 Windows、本机 Unreal Engine、隔离 workspace 和自研 Python runner。论文方法论中应保留的是对照实验、oracle、deterministic verifier、skill impact 指标和 trajectory 复盘，而不是原版工程载体。

## 3. Architecture

```text
benchmark.yaml
       │
       ▼
┌─────────────────────────────────────┐
│  runner                             │
│  preflight / validate-task /        │
│  run-single / run-matrix / report   │
└─────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│  workspace (per trial)              │
│  copy sample/TPSample → isolate     │
│  run setup.py                       │
└─────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│  agent adapter (codex / kimi-code   │
│  / manual / oracle / noop)          │
│  condition 决定注入哪些 skill        │
└─────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐   ┌─────────────────┐
│  build / automation execution       │──▶│  artifacts/     │
│  (ue-build / ue-autotest skill)     │   │  logs / reports │
└─────────────────────────────────────┘   └─────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│  verifier.py (deterministic)        │
│  只检查最终状态和产物               │
└─────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│  report generator                   │
│  skill impact analysis              │
└─────────────────────────────────────┘
```

核心原则：

- **Verifier 只验最终状态**：不读取 skill 目录，不依赖 agent 的过程声明。
- **Condition 控制 skill 注入**：实验组之间只有 skill 集合不同，其余环境保持一致。
- **Trial workspace 隔离**：每个 trial 复制 `sample/TPSample` 到独立目录，setup 只改 workspace。
- **Oracle 证明任务可解**：每个正式任务必须有稳定的 oracle baseline。

## 4. Components

### 4.1 Runner

位置：`benchmarks/ue5-skillsbench/runner/`

新增/调整子命令：

```bash
python -m benchmarks.ue5-skillsbench.runner preflight
python -m benchmarks.ue5-skillsbench.runner validate-task --task-id <id> --repeat 3
python -m benchmarks.ue5-skillsbench.runner run-single --task-id <id> --condition <c> --adapter <a>
python -m benchmarks.ue5-skillsbench.runner run-matrix --adapter <a> --run-id <id>
python -m benchmarks.ue5-skillsbench.runner report --run-id <id>
```

`run-matrix` 新增过滤参数：

- `--task-id <id>`：可重复。
- `--task-filter <tag|subcategory>`：按 `task.toml` 中的 tag 或 subcategory 过滤。
- `--condition <id>`：可重复。
- `--trials N`：覆盖 `benchmark.yaml` 默认值。
- `--run-id <id>`：标识一次矩阵运行。

`validate-task` 必须原子覆盖三段验收链：

```text
setup → verifier 失败或缺少必要产物
oracle → verifier 通过
重复 N 次均成立
```

内部复用 `run-single` 的 workspace/setup/verifier 逻辑，不单独重写流程。

约束：

- 任务声明了 oracle 但 `oracle.patch` / `oracle.py` 缺失时，必须判为验收失败，不允许静默降级为 noop。
- `type = "none"` 的 smoke 任务调用 `validate-task` 时直接报错退出，提示该任务不参与 oracle 验收。

### 4.2 Config (`benchmark.yaml`)

扩展为支持多 skill 和多 condition：

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

tasks:
  - path: benchmarks/ue5-skillsbench/tasks

trials: 3
```

Condition 设计决策：

- 不设 `all-ue-skills` condition：它与 `ue-autotest-with-build` 的 skill 集合完全相同，作为独立 condition 只会重复消耗 UE 构建时间。
- `ue-autotest-only` 保留定义但 MVP 不强制跑，未来用于回答"autotest skill 是否依赖 build skill 才有效"。

MVP 推荐 condition 矩阵：

| 任务类型 | 必跑 conditions | 可选 conditions |
| --- | --- | --- |
| build | `no-skills`, `ue-build-only`, `ue-autotest-with-build` | 无 |
| autotest authoring | `no-skills`, `ue-build-only`, `ue-autotest-with-build` | `ue-autotest-only` |
| autotest repair | `no-skills`, `ue-build-only`, `ue-autotest-with-build` | `ue-autotest-only` |
| autotest reporting | `no-skills`, `ue-autotest-with-build` | `ue-autotest-only` |

### 4.3 Workspace & Setup

每个 trial 的 workspace 目录结构：

```text
workspaces/<run-id>/<task-id>/<condition>/<trial-N>/
  TPSample/                  # 复制的项目
  artifacts/                 # runner 收集的产物
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

约束：

- `setup.py` 只修改 trial workspace，不修改 `sample/TPSample`。
- runner 负责把 workspace 中的 Automation report 复制到 `artifacts/automation/`，避免 trial workspace 被清理后无法复盘。
- `no-skills` 条件下 runner 必须确认 skills root 为空或不存在，并记录到 `result.json`。

### 4.4 Verifier

#### 4.4.1 统一输出结构

所有 verifier 通过共享 helper 构造并写出 `verifier_result.json`：

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

Schema 校验策略（fail loudly）：

- 必需顶层字段 `passed`、`failure_class`、`checks` 缺失或类型错误时，trial 判为 `verifier-error`。
- 允许 verifier 写出额外字段，不因未知字段报错。
- 校验由 runner 侧共享 helper 执行，任务 verifier 不各自手写 JSON 结构。

#### 4.4.2 Failure Class

统一跨任务 failure class：

| Class | 含义 |
| --- | --- |
| `setup` | fixture 注入失败 |
| `build` | 项目或测试模块无法编译 |
| `registration` | 测试模块未注册或 target 配置错误 |
| `automation-discovery` | 目标 scope 未发现测试或数量不足 |
| `test` | Automation 测试失败 |
| `reporting` | 测试通过但结构化或 Markdown 报告缺失 |
| `scope` | 运行了错误 scope，例如包含 performance tests |
| `cheating` | 删除测试、弱化断言、绕过 verifier 目标 |
| `agent-crash` | agent adapter 失败 |
| `timeout` | agent、build 或 verifier 超时 |
| `verifier-error` | verifier 自身异常或输出 schema 错误 |

#### 4.4.3 Automation Report 解析

`ue-autotest` 任务 verifier 应使用共享 parser，而不是每个任务复制解析逻辑。

解析优先级：

1. `Saved/Automation/Reports/**/index.json`
2. `Saved/Automation/autotest_results.json`
3. editor log 中的 Automation summary

约束：

- 允许宽容字段读取。
- 不允许在无法确认测试结果时判定通过。
- 解析路径必须写入 `checks` 或 `automation.report_parser`。

### 4.5 Oracle

#### 4.5.1 类型

| Type | 文件 | 适用场景 |
| --- | --- | --- |
| `patch` | `oracle.patch` | build repair、test authoring、bug repair |
| `action` | `oracle.py` / `oracle.ps1` | scoped report 等无代码变更任务 |
| `none` | 无 | smoke/preflight，不进入 skill impact 统计 |

#### 4.5.2 验收链

每个正式任务必须满足：

```text
setup 后 verifier 失败或缺少必要产物
oracle 后 verifier 通过
以上两段重复 3 次均成立
```

Oracle 作用：

- 证明任务可解。
- 证明 verifier 没有误判。
- 证明 setup 产生了预期失败态。
- 证明任务难度来自 UE 工作流，而不是 fixture 损坏或环境漂移。

### 4.6 Report

固定生成：

```text
reports/<run-id>-results.json
reports/<run-id>-summary.md
reports/<run-id>-failures.md
```

#### 4.6.1 必需指标

每个 task × condition：

- trials
- passed
- pass rate
- mean / median wall-clock
- mean build duration
- mean verifier duration
- failure class distribution
- mean files changed / lines changed

每个 task 的 condition 对比：

- delta percentage points
- normalized gain
- speedup / slowdown
- 是否存在新增 failure class

每个 skill 的聚合：

- 相关任务 pass-rate gain
- 非相关任务是否出现负迁移
- 最常见失败类型

#### 4.6.2 `failures.md`

列出失败 trial 的：

- task
- condition
- trial
- failure class
- verifier failed checks
- artifacts 路径
- diff 路径

### 4.7 Trajectory 观测

过程指标分两档。MVP 只收第一档：

- agent wall-clock seconds
- build/verifier duration
- adapter exit code 与 timeout
- git diff 文件数、增删行
- 是否产生 Automation report

第二档预留字段，统一填 `"unknown"`：

- `command_invocations`：build 或 Automation 命令执行次数
- `skill_file_reads`：skill 文件访问记录

MVP 不做 stdout 正则猜测——从 stdout 匹配命令字符串不等于命令被执行，产出看似精确实则错误的数据比缺数据更糟。

## 5. Data Formats

### 5.1 标准任务目录

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

- `instruction.md` 是 agent 唯一看到的任务说明，不直接说"使用某 skill"。
- `setup.py` 只修改 trial workspace。
- `verifier.py` 只检查最终项目状态和 artifacts。

### 5.2 `task.toml` 字段

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

### 5.3 `result.json`

每次 trial 生成，记录实验配置和过程指标：

```json
{
  "run_id": "2026-07-04-001",
  "task_id": "tps-autotest-run-scoped-report",
  "condition": "ue-autotest-with-build",
  "trial": 1,
  "adapter": "codex",
  "skills_injected": [
    {
      "name": "ue-build",
      "source": "skills/ue-build",
      "destination": "workspaces/.../skills/ue-build"
    }
  ],
  "agent": {
    "exit_code": 0,
    "timed_out": false,
    "wall_clock_seconds": 420.1
  },
  "build": {
    "duration_seconds": 123.4,
    "log": "build.log"
  },
  "verifier": {
    "duration_seconds": 45.2,
    "result": "verifier_result.json"
  },
  "git": {
    "files_changed": 3,
    "insertions": 120,
    "deletions": 5
  },
  "trajectory": {
    "command_invocations": "unknown",
    "skill_file_reads": "unknown"
  }
}
```

## 6. CLI

| 子命令 | 作用 | 关键参数 |
| --- | --- | --- |
| `preflight` | 检查 UE 环境、Python 依赖、skill 路径 | 无 |
| `validate-task` | 三段 oracle 验收链 | `--task-id`, `--repeat` |
| `run-single` | 跑一次 trial | `--task-id`, `--condition`, `--adapter`, `--trial` |
| `run-matrix` | 按配置跑完整矩阵 | `--adapter`, `--run-id`, `--task-id`, `--task-filter`, `--condition`, `--trials` |
| `report` | 生成报告 | `--run-id` |

## 7. Task Catalog

### 7.1 Build 任务

| 任务 ID | 处理 |
| --- | --- |
| `tps-build-basic` | 标记为 smoke，不计入正式 skill impact 统计 |
| `tps-build-engine-resolve` | 保留为正式 `ue-build` 任务 |
| `tps-build-incremental` | 暂保留为正式任务；Phase A 验收时确认其 setup/verifier 是否构造了 skill 敏感场景。若否，降级为 smoke，需再新增一个 repair 型任务补足 3 个正式 build 任务 |
| `tps-build-fix-module-dependency`（新增） | 正式任务：setup 注入 module dependency / `Build.cs` / `Target.cs` 缺陷导致编译或链接失败，agent 需定位并修复 |

正式 build 任务应优先是 repair 型，而不是单纯"请编译项目"——后者大概率 `no-skills` 也能通过，测不出 skill impact。

### 7.2 ue-autotest 任务

按以下顺序落地：

1. `tps-autotest-run-scoped-report`：先做，不需要代码修改，能最早打通 Automation report 收集和 verifier 解析。
2. `tps-autotest-add-input-math-tests`：验证 test module 创建、注册和 headless 运行。
3. `tps-autotest-fix-failing-error-tests`：补防作弊和弱化断言检测。

三个任务的具体 fixture、verifier 要求和 oracle 形状参见 `docs/ue-autotest-benchmark-tasks-design.md`。本 spec 只规定框架必须提供的支持能力。

## 8. Testing

新增不依赖真实 UE 的 runner 自测：

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

## 9. Milestones

### Phase A：框架协议固化

- 更新 `benchmark.yaml`，加入 `ue-autotest` 和组合 conditions。
- 定义 verifier result schema 与共享校验 helper。
- 定义 oracle 类型和 task authoring 约定，实现 `validate-task` 命令。
- 审查 `tps-build-incremental` 是否构造了 skill 敏感场景，决定保留或降级为 smoke。
- 修正 README 与过时 MVP 文档标记。

验收：现有 build tasks 仍可 discovery，report 不回归；`validate-task` 能对现有任意一个 build 任务完成三段验收。

### Phase B：Automation report 管线

- 实现共享 Automation report parser。
- 实现 artifacts 复制到 `artifacts/automation/`。
- 落地 `tps-autotest-run-scoped-report`。
- oracle action 能生成报告并通过 verifier。

验收：`tps-autotest-run-scoped-report` 通过 `validate-task --repeat 3`，错误 scope 能被 verifier 拒绝。

### Phase C：Autotest authoring 与 repair

- 落地 `tps-autotest-add-input-math-tests`。
- 落地 `tps-autotest-fix-failing-error-tests`。
- 落地 `tps-build-fix-module-dependency`（新增 build repair 任务）。
- 补防作弊检查：删除测试、弱化断言、跳过目标 scope。

验收：三个 `ue-autotest` 任务与新增 build 任务的 oracle 均通过 `validate-task --repeat 3`。

### Phase D：实验矩阵与报告

- 增加 task/condition filter。
- 报告新增 failure detail 与 skill impact 聚合。
- 跑 2 tasks × 2 conditions × 2 trials 的真实 agent smoke matrix。

验收：报告能清楚比较 `no-skills` 与 skill condition 的差异，并能复盘每个失败 trial。

### Phase E：Runner 自测

- 新增不依赖 UE 的 runner 单元测试。
- 在本地 CI 或手动命令中固定执行。

验收：配置解析、task discovery、report aggregation、schema 校验都有测试覆盖。

## 10. Decision Records

1. **不设 `all-ue-skills` condition**：与 `ue-autotest-with-build` 完全重复，MVP 为 4 个 conditions；`ue-autotest-only` 保留定义但不强制跑。
2. **oracle 验收合并为单个 `validate-task --repeat 3` 命令**：一条命令原子覆盖"setup 失败 → oracle 通过 × N 轮"，不拆为两个命令；声明 oracle 但文件缺失判为失败。
3. **trajectory 指标 MVP 只收 runner 可直接观测的第一档**：`command_invocations`、`skill_file_reads` 预留字段填 `unknown`，不做 stdout 正则猜测。
4. **build 任务账**：`tps-build-basic` 降为 smoke，新增 `tps-build-fix-module-dependency` 补足 3 个正式任务；`tps-build-incremental` 的 skill 敏感性确认纳入 Phase A 验收。
5. **verifier schema 由共享 helper 校验**：必需字段缺失 fail loudly（判 `verifier-error`），允许额外字段；Automation report 解析为共享 helper。
6. **实现顺序以本文为准**：`run-scoped-report` 先行以降低 Automation report 管线风险，覆盖任务设计文档中的"authoring 先行"顺序。

## 11. Completion Criteria

框架补全完成时，应满足：

- `ue-build` 与 `ue-autotest` 都有正式任务覆盖。
- 每个正式任务有 oracle baseline。
- 每个正式任务有 deterministic verifier。
- `no-skills`、单 skill、组合 skill 至少能形成一组可比较结果。
- report 能展示 pass rate、normalized gain、耗时、失败分布和失败复盘入口。
- artifacts 能独立支持人工复盘。
- 文档不再把读者引向过时 PowerShell MVP 或原版 BenchFlow 兼容目标。

达到以上标准后，当前项目可以称为"UE5 场景迁移版 SkillsBench MVP"。

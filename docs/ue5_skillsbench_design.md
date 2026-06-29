# UE5 SkillsBench 设计稿

日期：2026-06-12

## 背景

本设计基于 [`docs/ue5_skillsbench.md`](./ue5_skillsbench.md) 的调研结论：UE5 workflow skills 适合用 SkillsBench 的 outcome-based 思路评估，但当前不宜直接套用上游 Harbor/Docker 任务形态。第一阶段应做一个本地私有、Windows + PowerShell + UE5 兼容的 SkillsBench-compatible harness。

当前仓库里需要纳入第一版基准测试的 skills：

- `skills/ue-build`
- `skills/ue-lsp`
- `skills/ue-autotest`

第一版测试项目固定为：

- `sample/TPSample/TPSample.uproject`
- `EngineAssociation = 5.7`
- Editor target: `TPSampleEditor`
- Runtime module: `TPSample`

## 目标

第一版 UE5 SkillsBench 要回答一个具体问题：

> 在同一个 `sample/TPSample` 基线项目上，给 agent 注入 `ue-build`、`ue-lsp`、`ue-autotest` 后，是否比无 skills 条件更稳定地完成 UE5 构建修复、API/符号定位、自动化测试编写与修复任务？

MVP 范围：

- 使用本地 Windows runner，不依赖 Docker。
- 使用 `sample/TPSample` 作为只读基线项目。
- 每个 trial 创建独立工作副本，不直接修改 `sample/TPSample`。
- 支持 `no-skills`、`all-ue-skills` 和按需 ablation 条件。
- 每个任务使用 deterministic verifier 判定 pass/fail。
- 输出 pass rate、delta、normalized gain、耗时、失败分类和运行产物路径。

非目标：

- 第一版不追求上游 SkillsBench 完全兼容。
- 第一版不发布包含 UE Engine 的公开镜像。
- 第一版不把 skill usage 当主指标。
- 第一版不评估 Blueprint 图编辑、渲染正确性或需要真实 GPU/GUI 的任务。

## 现状约束

### `ue-build`

`ue-build` 已有可执行脚本：

- `skills/ue-build/build.ps1`
- 自动解析 `.uproject` 的 `EngineAssociation`
- 默认构建 `Development Editor`
- 通过 `Build.bat <Project>Editor Win64 Development <Project.uproject> -waitmutex` 构建

适合作为 verifier 或 agent 操作的环境信号，但 verifier 不应直接依赖 skill 目录。为避免泄漏技能内容，benchmark verifier 应内置一份最小 UBT 调用逻辑，或放在 `benchmarks/ue5-skillsbench/verifiers/lib/Unreal.ps1`。

### `ue-lsp`

`ue-lsp` 目前主要是 skill 说明和配置：

- `skills/ue-lsp/SKILL.md`
- `skills/ue-lsp/config.yaml`

`SKILL.md` 提到的 `scripts/status.ps1` 当前仓库中不存在。因此第一版不能把 LSP 状态脚本作为硬依赖。MVP 中 `ue-lsp` 的评估方式应是：

- agent 是否能借助 skill 说明选择正确的 UE C++ 符号定位/验证流程。
- 最终修复由 build/static verifier 判定。
- skill usage 只作为辅助 telemetry，且 Codex 类 harness 标记为 partial confidence。

后续可以补齐：

- `skills/ue-lsp/scripts/status.ps1`
- 生成/检测 `compile_commands.json` 的本地脚本
- clangd health check 和 diagnostics capture

### `ue-autotest`

`ue-autotest` 已有可执行脚本：

- `skills/ue-autotest/scripts/autotest.ps1`
- `skills/ue-autotest/scripts/report.ps1`
- `skills/ue-autotest/testing-patterns.md`

脚本会扫描 `Source/*Test/*.Build.cs`，先调用 `ue-build` 编译，再运行 `UnrealEditor-Cmd.exe` automation tests，并输出：

- `Saved/Automation/autotest_results.json`
- `Saved/Automation/Reports/...`

当前 `sample/TPSample` 没有测试模块，Editor target 只注册了 `TPSample`。因此 autotest 任务必须由 fixture 提供待修复的测试模块，或明确要求 agent 创建并注册 `TPSampleTest` Editor 模块。

## 总体架构

建议新增目录：

```text
benchmarks/
└── ue5-skillsbench/
    ├── README.md
    ├── benchmark.yaml
    ├── runner/
    │   ├── run.ps1
    │   ├── adapters/
    │   │   ├── oracle.ps1
    │   │   ├── codex.ps1
    │   │   ├── claude-code.ps1
    │   │   └── opencode.ps1
    │   └── lib/
    │       ├── ProjectCopy.ps1
    │       ├── SkillInjection.ps1
    │       ├── Metrics.ps1
    │       └── Unreal.ps1
    ├── tasks/
    │   └── <task-id>/
    │       ├── instruction.md
    │       ├── task.toml
    │       ├── setup.ps1
    │       ├── oracle.patch
    │       ├── verifier.ps1
    │       └── fixtures/
    └── reports/
```

运行时目录放到 `.bench/`，不进入版本管理：

```text
.bench/
└── runs/
    └── <run-id>/
        └── <task-id>/
            └── <condition>/
                └── trial-<n>/
                    ├── workspace/
                    │   ├── TPSample/
                    │   ├── instruction.md
                    │   └── skills/              # 仅 skills 条件存在
                    ├── artifacts/
                    │   ├── agent.stdout.log
                    │   ├── agent.stderr.log
                    │   ├── verifier.stdout.log
                    │   ├── verifier.stderr.log
                    │   ├── git.diff
                    │   ├── build.log
                    │   └── automation/
                    └── result.json
```

关键原则：

- `sample/TPSample` 是只读基线。
- runner 每次复制一个干净副本到 run workspace。
- 复制时排除 UE 生成目录：`Binaries`、`DerivedDataCache`、`Intermediate`、`Saved`。
- task 的 `setup.ps1` 只修改 run workspace。
- `no-skills` 条件的 workspace 中不能包含仓库根目录的 `skills/`。
- skills 条件只复制被允许的 skill 目录到 run workspace 的 skills root。
- verifier 不读取 skill 目录，不调用 agent，不根据过程评分。

## 配置模型

`benchmark.yaml` 建议结构：

```yaml
project:
  source: sample/TPSample
  uproject: TPSample.uproject
  engineAssociation: "5.7"
  platform: Win64
  configuration: Development
  target: TPSampleEditor

copy:
  exclude:
    - Binaries
    - DerivedDataCache
    - Intermediate
    - Saved

skills:
  ue-build:
    path: skills/ue-build
  ue-lsp:
    path: skills/ue-lsp
  ue-autotest:
    path: skills/ue-autotest

conditions:
  no-skills:
    skills: []
  all-ue-skills:
    skills: [ue-build, ue-lsp, ue-autotest]
  build-only:
    skills: [ue-build]
  build-lsp:
    skills: [ue-build, ue-lsp]
  build-autotest:
    skills: [ue-build, ue-autotest]

execution:
  trialsPerCondition: 3
  agentTimeoutMinutes: 45
  verifierTimeoutMinutes: 30
  cachePolicy: project-clean-engine-warm
```

任务 `task.toml` 建议结构：

```toml
id = "tps-build-module-dependency-repair"
project = "TPSample"
timeout_minutes = 45
primary_skills = ["ue-build"]
secondary_skills = ["ue-lsp"]

[metadata]
difficulty = "medium"
category = "software-engineering"
subcategory = "build-repair"
category_confidence = "high"
task_type = ["repair", "debugging"]
modality = ["source-code"]
interface = ["terminal", "compiler-toolchain"]
skill_type = ["tool-workflow", "debugging-heuristic"]
tags = ["unreal-engine", "ue5", "ubt", "uht", "tpsample"]

[verifier]
script = "verifier.ps1"
pass_condition = "exit_code == 0"
```

## Runner 流程

1. 读取 `benchmark.yaml`，解析任务、条件、trial 数。
2. 执行 preflight：
   - PowerShell 版本 >= 5.1
   - `git` 可用
   - `sample/TPSample/TPSample.uproject` 存在
   - UE 5.7 registry entry 可解析
   - `Build.bat` 和 `UnrealEditor-Cmd.exe` 存在
3. 为每个 task/condition/trial 创建 run workspace。
4. 复制 `sample/TPSample` 到 workspace，排除生成目录。
5. 在 workspace 内初始化 git，用于记录 agent diff。
6. 执行 task `setup.ps1`，注入破损代码、缺失测试或配置问题。
7. 根据 condition 注入 skills：
   - `no-skills`：不复制任何 skill，不提供 skill prompt。
   - `all-ue-skills`：复制三个 skill。
   - ablation：只复制配置中的 skill。
8. 调用 agent adapter：
   - `oracle` adapter 应用 `oracle.patch`，用于验证任务可解。
   - 真实 agent adapter 读取 `instruction.md`，在 workspace 内运行。
9. agent 结束后收集 git diff、stdout/stderr、耗时。
10. 执行 `verifier.ps1`。
11. 写入 `result.json`。
12. 汇总生成 markdown/JSON report。

## Agent Adapter

Adapter 的职责是把同一任务转成不同 agent/harness 的执行方式。

统一输入：

- `WorkspaceRoot`
- `InstructionPath`
- `SkillsRoot`
- `Condition`
- `TimeoutMinutes`
- `ArtifactsDir`

统一输出：

- `exitCode`
- `timedOut`
- `stdoutLog`
- `stderrLog`
- `startedAt`
- `endedAt`
- `harnessMetadata`

建议先实现：

- `oracle`：应用 `oracle.patch`，验证任务和 verifier。
- `manual`：暂停等待人工/外部 agent 修改 workspace，用于调试。
- `codex`：后续接入 Codex CLI 或本地可用 harness。

Skill 注入应由 adapter 适配：

- Claude Code/OpenCode/OpenHands：使用各自原生 skill path 或 tool surface。
- Codex：若无法使用原生 skill loader，第一版可用 adapter 把选中 skill 的 `SKILL.md` 和必要文件作为 prompt fragment 注入，但报告中必须记录 `skill_invocation_confidence = "partial"`。

## Verifier 设计

Verifier 必须 outcome-based。统一约定：

- exit code 0 表示 pass。
- exit code 非 0 表示 fail。
- 所有 verifier 输出结构化 `verifier_result.json`。
- verifier 可以运行 UBT、UHT、UnrealEditor-Cmd 和静态检查。
- verifier 不读取 `workspace/skills`。
- verifier 不根据 agent 是否调用某个 skill 判定通过。

建议 `verifier_result.json`：

```json
{
  "passed": true,
  "failureClass": null,
  "checks": [
    {
      "name": "ubt_build",
      "passed": true,
      "durationMs": 123456,
      "details": "TPSampleEditor Development Win64 built successfully"
    }
  ],
  "artifacts": {
    "buildLog": "artifacts/build.log",
    "automationResults": null
  }
}
```

失败分类：

- `build`
- `uht`
- `test`
- `timeout`
- `wrong-fix`
- `environment`
- `agent-crash`
- `verifier-error`

## MVP 任务集

第一版建议做 3 个正式任务和 1 个环境 smoke task。

### 0. `tps-env-build-smoke`

用途：验证 runner、UE 路径和 `TPSample` 基线可构建。

是否计入 benchmark：否。

Setup：

- 不修改项目。

Verifier：

- 构建 `TPSampleEditor Win64 Development`。
- 检查 exit code 为 0。

### 1. `tps-build-module-dependency-repair`

主要评估：`ue-build`

辅助评估：`ue-lsp`

任务目标：

- `TPSample` 中存在一个由 fixture 注入的构建错误。
- 错误来自 UE 模块依赖或 include 配置不完整。
- agent 需要定位 UBT/UHT 日志里的根因，做最小修复。

建议 setup：

- 在 `Source/TPSample/TPSample.Build.cs` 中移除某个已被源码使用的依赖，例如 `UMG`、`AIModule` 或 `GameplayStateTreeModule`。
- 或新增一个小型 C++ 文件引用某个 UE 模块 API，但故意不添加对应 module dependency。

Instruction 只描述：

- 项目当前无法构建。
- 请修复，使 `TPSampleEditor` Development build 通过。
- 不要删除功能代码。

Verifier：

- 运行独立 UBT 构建。
- 检查 exit code 为 0。
- 检查日志中没有 `error C`、`fatal error`、`UnrealHeaderTool failed`、`error LNK`。
- 静态检查被测功能文件仍存在，不能通过删除代码绕过。

### 2. `tps-lsp-api-signature-repair`

主要评估：`ue-lsp`

辅助评估：`ue-build`

任务目标：

- fixture 注入一个 UE C++ API 调用签名或类型使用错误。
- agent 需要通过符号、引用、签名或相似代码定位正确用法。
- 最终修复必须构建通过。

建议 setup：

- 修改 `TPSampleCharacter.cpp` 中 Enhanced Input 相关调用，使其使用错误 overload 或错误参数类型。
- 或新增一个 helper 调用 UE API 时使用过期/错误签名。

Instruction 只描述：

- 项目中有一个 UE C++ API 使用错误。
- 请确认正确签名并修复。
- 不要大范围重写输入系统。

Verifier：

- 运行 UBT build。
- 静态检查目标错误调用文本不再出现。
- 可选：检查修复仍保留原有方法名和绑定逻辑。

注意：

- 由于 `ue-lsp` 当前没有可执行状态脚本，第一版不要求 verifier 证明 agent 真的调用了 LSP。
- 该任务用最终代码结果评估 skill 是否帮助 agent 完成 API 定位流程。

### 3. `tps-autotest-add-character-tests`

主要评估：`ue-autotest`

辅助评估：`ue-build`

任务目标：

- agent 需要为 `TPSample` 创建并注册一个 Editor test module。
- 新增至少 3 个 UE Automation tests：happy path、edge、regression。
- 使用 `ue-autotest` 约定的命名、scope 和运行方式。

建议 setup：

- fixture 新增一个纯 C++、低依赖的 helper，例如 `FTPSampleMovementInput` 或 `FTPSampleInputMath`。
- helper 放在 runtime module，便于无 world/nullrhi 测试。
- 不预置 test module，让 agent 创建 `TPSampleTest`。

Instruction 只描述：

- 为指定 helper 添加 UE Automation tests。
- 覆盖 happy path、edge、regression 三类场景。
- 测试必须能通过 headless Automation。

Verifier：

- 检查存在 `Source/TPSampleTest/TPSampleTest.Build.cs`。
- 检查 `.uproject` 中注册 `TPSampleTest`，类型为 `Editor`。
- 检查 `TPSampleEditor.Target.cs` 包含 `TPSampleTest`。
- 构建 Editor target。
- 运行 `UnrealEditor-Cmd.exe` 指定 automation scope，例如 `TPSample.Input.*`。
- 解析 `Saved/Automation/autotest_results.json` 或 UE 原生 `index.json`。
- 要求至少 3 个目标测试，且全部 pass。

### 4. `tps-autotest-fix-failing-test`

阶段：MVP 后扩展。

主要评估：`ue-autotest`

任务目标：

- fixture 预置一个已注册的 `TPSampleTest` 模块和失败测试。
- agent 判断是测试代码错误还是生产代码错误，并做最小修复。

Verifier：

- 运行相同 automation scope。
- 检查失败数为 0。
- 检查目标测试没有被删除。
- 检查断言数量或关键断言文本没有被削弱。

## 指标

主指标：

- `pass_rate`
- `delta_pp = pass_rate_with_skills - pass_rate_no_skills`
- `normalized_gain = (pass_skill - pass_vanilla) / (1 - pass_vanilla)`

辅助指标：

- `wall_clock_seconds`
- `agent_exit_code`
- `verifier_exit_code`
- `failure_class`
- `files_changed_count`
- `lines_added`
- `lines_deleted`
- `build_duration_seconds`
- `automation_total`
- `automation_passed`
- `automation_failed`

Skill usage telemetry：

- `skills_available`
- `skill_invocation_surface`
- `skill_usage_observed`
- `skill_usage_confidence`

Codex 类 harness 的 skill usage confidence 默认不高于 `partial`，因为其 skill 注入不一定表现为显式 tool call。

## 结果格式

单个 trial 的 `result.json`：

```json
{
  "runId": "20260612-001",
  "taskId": "tps-build-module-dependency-repair",
  "condition": "all-ue-skills",
  "trial": 1,
  "agent": {
    "name": "codex",
    "model": "gpt-5",
    "exitCode": 0,
    "timedOut": false,
    "startedAt": "2026-06-12T10:00:00+08:00",
    "endedAt": "2026-06-12T10:08:31+08:00"
  },
  "skills": {
    "available": ["ue-build", "ue-lsp", "ue-autotest"],
    "usageObserved": ["ue-build"],
    "usageConfidence": "partial"
  },
  "verifier": {
    "passed": true,
    "exitCode": 0,
    "failureClass": null
  },
  "metrics": {
    "wallClockSeconds": 511,
    "buildDurationSeconds": 132,
    "filesChanged": 1,
    "linesAdded": 1,
    "linesDeleted": 0
  },
  "artifacts": {
    "workspace": ".bench/runs/...",
    "diff": "artifacts/git.diff",
    "verifierResult": "artifacts/verifier_result.json"
  }
}
```

汇总报告：

```text
task_id, condition, trials, pass_rate, delta_pp, normalized_gain, mean_seconds, top_failure_class
```

## 缓存与公平性

UE 构建时间受缓存影响很大。第一版建议采用：

- 项目副本每次 clean，不复制 `Binaries/Intermediate/Saved/DerivedDataCache`。
- 不清理全局 Engine cache 和机器级 DDC。
- 每次记录 `cachePolicy = project-clean-engine-warm`。
- 时间指标只做辅助，不作为第一阶段主排名依据。

如果后续要比较耗时，应增加独立模式：

- `cold-project-cold-ddc`
- `clean-project-warm-ddc`
- `incremental-project-warm-ddc`

## 安全边界

runner 必须校验所有删除/清理操作都发生在 `.bench/runs/<run-id>` 内。

允许清理：

- run workspace 内复制出来的项目目录
- run workspace 内 UE 生成目录
- run artifacts

不允许自动清理：

- `sample/TPSample`
- 仓库根目录
- Engine 安装目录
- 用户全局 DerivedDataCache

## 实施顺序

1. 添加 `.bench/` 到 `.gitignore`。
2. 创建 `benchmarks/ue5-skillsbench/` 目录和 `benchmark.yaml`。
3. 实现 `runner/lib/ProjectCopy.ps1`，只复制 `sample/TPSample` 的必要文件。
4. 实现 `runner/lib/Unreal.ps1`，独立解析 UE 5.7 路径并执行 UBT/UnrealEditor-Cmd。
5. 实现 `tps-env-build-smoke`，确认本机环境可构建基线项目。
6. 实现 `oracle` adapter 和 `oracle.patch` 验证链路。
7. 实现第一个正式任务 `tps-build-module-dependency-repair`。
8. 扩展 `tps-lsp-api-signature-repair`。
9. 扩展 `tps-autotest-add-character-tests`，补齐 test module 验证。
10. 接入真实 agent adapter，先跑 `no-skills` vs `all-ue-skills` 各 3 次。
11. 生成汇总报告，再决定是否做 ablation 和更多任务。

## 验收标准

MVP 完成时应满足：

- `sample/TPSample` 没有被 runner 修改。
- smoke task oracle/verifier 通过。
- 3 个正式任务的 oracle 通过率为 100%。
- 至少一个 agent 在 `no-skills` 与 `all-ue-skills` 条件下各完成 3 次 trial。
- 汇总报告包含 pass rate、delta_pp、normalized_gain、平均耗时和失败分类。
- 任一失败 trial 都能追溯到 workspace、diff、agent log、verifier log 和结构化结果。

## 已知风险

- UE 5.7 安装路径依赖 Windows registry；CI/新机器需要 preflight 明确报错。
- `ue-lsp` 的可执行状态脚本缺失，第一版只能以最终任务结果间接评估。
- `ue-autotest` 任务需要创建或预置 `TPSampleTest`，否则当前样例项目没有可运行测试模块。
- Codex 的 skill usage telemetry 不一定完整，不能把 usage count 作为主指标。
- UE 构建缓存会影响耗时，第一阶段不要把速度当主要排名依据。

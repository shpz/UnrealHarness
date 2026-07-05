# Phase 01 - Harness Foundation

## 目标

建立 UE5 SkillsBench MVP 的本地 runner 基础设施。这个阶段不实现正式 benchmark task，不接入真实 agent，只把目录结构、配置模型、项目复制、安全边界和结果骨架准备好。

## 前置条件

- 当前仓库已初始化 git。
- `.gitignore` 已忽略 `.bench/` 和 UE 生成目录。
- `sample/TPSample/TPSample.uproject` 存在。
- `skills/ue-build`、`skills/ue-lsp`、`skills/ue-autotest` 存在。

## 执行与审核

- 执行 subagent：负责完成本阶段 runner 基础设施、配置模型、项目复制、安全边界和结果骨架；不得实现正式 task、运行 UBT 或接入真实 agent。
- subagent 交回内容：变更摘要、`run.ps1`/preflight 的验证命令与输出、项目复制样例路径、安全路径拒绝用例结果。
- 主 agent 审核重点：目录结构是否符合交付物清单、`benchmark.yaml` 是否声明完整、复制排除规则是否正确、安全清理函数是否拒绝仓库根目录和 `sample/TPSample`。

## 交付物

- `benchmarks/ue5-skillsbench/README.md`
- `benchmarks/ue5-skillsbench/benchmark.yaml`
- `benchmarks/ue5-skillsbench/runner/run.ps1`
- `benchmarks/ue5-skillsbench/runner/lib/ProjectCopy.ps1`
- `benchmarks/ue5-skillsbench/runner/lib/SkillInjection.ps1`
- `benchmarks/ue5-skillsbench/runner/lib/Unreal.ps1`
- `benchmarks/ue5-skillsbench/runner/lib/Metrics.ps1`

## 工作项

1. 创建 `benchmarks/ue5-skillsbench/` 目录结构。
2. 在 `benchmark.yaml` 中声明：
   - 基线项目：`sample/TPSample`
   - `.uproject`：`TPSample.uproject`
   - target：`TPSampleEditor`
   - platform：`Win64`
   - configuration：`Development`
   - skills：`ue-build`、`ue-lsp`、`ue-autotest`
   - conditions：`no-skills`、`all-ue-skills`
3. 实现 preflight：
   - PowerShell 版本 >= 5.1
   - `git` 可用
   - `sample/TPSample` 存在
   - UE 5.7 registry entry 可解析
   - `Build.bat` 和 `UnrealEditor-Cmd.exe` 存在
4. 实现项目复制：
   - 从 `sample/TPSample` 复制到 `.bench/runs/<run-id>/.../workspace/TPSample`
   - 排除 `Binaries`、`DerivedDataCache`、`Intermediate`、`Saved`
   - 不排除 `Build`
5. 实现安全路径校验：
   - 所有清理操作必须限制在 `.bench/runs/<run-id>` 内
   - 拒绝空路径、仓库根目录、`sample/TPSample`、Engine 目录
6. 在 workspace 内初始化 git，用于记录 agent diff。
7. 定义 `result.json` 基础字段和 artifacts 目录布局。

## 验收标准

- `run.ps1` 能读取 `benchmark.yaml` 并输出已解析配置。
- preflight 失败时能给出明确错误，不产生半初始化 workspace。
- project copy 后 workspace 内存在 `TPSample.uproject` 和 `Source/TPSample`。
- project copy 后 workspace 内不存在复制来的 `Binaries`、`DerivedDataCache`、`Intermediate`、`Saved`。
- workspace 内 git 初始化成功，可生成 clean status。
- 任意清理函数传入仓库根目录或 `sample/TPSample` 时会拒绝执行。

## 暂不处理

- 不实现正式 task。
- 不运行 UBT。
- 不接入真实 agent。
- 不生成最终 benchmark 报告。

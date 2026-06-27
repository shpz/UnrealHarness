# Phase 02 - Smoke And Oracle

## 目标

跑通最小闭环：runner 创建 workspace，执行一个不修改项目的 smoke task，通过 oracle adapter 和 verifier 构建 `TPSampleEditor`。这个阶段用于确认本机 UE 环境、runner artifact、verifier 输出和 oracle 流程可靠。

## 前置条件

- Phase 01 已完成。
- preflight 能解析 UE 5.7 引擎路径。
- `sample/TPSample` 基线项目可在本机环境中构建。

## 执行与审核

- 执行 subagent：负责实现 oracle/manual adapter、smoke task、UBT 构建封装和 verifier 输出；不得接入 `skills/`、正式破坏性 fixture 或 benchmark 汇总。
- subagent 交回内容：smoke task 的 oracle 运行记录、workspace 隔离证据、`result.json` 与 `verifier_result.json` 示例、构建日志路径。
- 主 agent 审核重点：oracle 无 patch 时能直接进入 verifier、manual adapter 不绕过 verifier、构建日志和 result schema 完整、`sample/TPSample` 未被修改。

## 交付物

- `benchmarks/ue5-skillsbench/runner/adapters/oracle.ps1`
- `benchmarks/ue5-skillsbench/runner/adapters/manual.ps1`
- `benchmarks/ue5-skillsbench/tasks/tps-env-build-smoke/instruction.md`
- `benchmarks/ue5-skillsbench/tasks/tps-env-build-smoke/task.toml`
- `benchmarks/ue5-skillsbench/tasks/tps-env-build-smoke/setup.ps1`
- `benchmarks/ue5-skillsbench/tasks/tps-env-build-smoke/verifier.ps1`

## 工作项

1. 实现 `oracle` adapter：
   - 如果任务有 `oracle.patch`，在 workspace 内应用 patch。
   - 如果任务没有 patch，直接进入 verifier。
   - 记录 stdout、stderr、exit code 和耗时。
2. 实现 `manual` adapter：
   - 创建 workspace 后暂停，允许人工或外部 agent 修改。
   - 继续后执行 verifier。
3. 实现 `tps-env-build-smoke`：
   - `setup.ps1` 为 no-op。
   - `instruction.md` 只说明需要确认项目可构建。
   - `verifier.ps1` 调用独立 UBT 构建逻辑。
4. 在 `Unreal.ps1` 中实现：
   - 从 `.uproject` 读取 `EngineAssociation`
   - 从 registry 解析 Engine root
   - 定位 `Build.bat`
   - 构建 `TPSampleEditor Win64 Development`
   - 写入 `artifacts/build.log`
5. 输出 `verifier_result.json`。

## 验收标准

- `tps-env-build-smoke` 使用 `oracle` adapter 可通过。
- `tps-env-build-smoke` 的 workspace 与 `sample/TPSample` 内容隔离。
- 构建日志保存到 artifacts。
- `result.json` 包含 agent、verifier、metrics、artifacts 四类信息。
- verifier exit code 为 0 时任务 pass；非 0 时任务 fail。
- smoke task 不计入正式 benchmark 汇总。

## 暂不处理

- 不接入 `skills/`。
- 不实现正式破坏性 fixture。
- 不计算 pass rate 或 normalized gain。
- 不优化 UE 构建耗时。

## 风险

- 如果本机 UE 5.7 registry 缺失，Phase 02 会阻塞。处理方式是在 preflight 中给出明确的 EngineAssociation 和 registry key 提示，不在 runner 内猜测 Engine 路径。

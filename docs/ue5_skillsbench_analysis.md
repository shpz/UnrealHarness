# UE5 SkillsBench 结果失真分析

## 核心结论

上一版 PowerShell 实现（`UnrealHarnessBenchPS`）的基准测试报告与体感差距大，主要体现在：

1. **Verifier 构建被缓存掩盖，耗时仅 ~1 秒，完全失真**
2. **Agent 崩溃但 verifier 判定通过，状态判定脱节**
3. **任务设计区分度不足，no-skills 也能 100% 通过**
4. **Skill 注入后没有观察到 usage，无法验证 skill 是否真正被使用**

---

## 1. Verifier 构建缓存失真（最严重）

### 现象

从 `uebuild-skillflow-20260614-5x-results.json`：

| condition | meanBuildDurationSeconds |
|-----------|--------------------------|
| no-skills | 0.936 |
| ue-build-only | 0.966 |

一个 UE5 第三人称模板项目的完整 Development Editor 构建，不可能在 1 秒内完成。这说明 verifier 阶段的 `Build.bat` 调用走了**增量编译捷径**，没有真正重新编译。

### 根因

`verifier.ps1` 直接调用 `Invoke-UnrealBuild`（即 `Build.bat <Target> Win64 Development <uproject> -waitmutex`），没有：

- 清理 `Intermediate`、`Binaries` 或 `Saved`
- 使用 `-Rebuild` 或 `-Clean` 标志
- 验证是否真正执行了编译/链接步骤

如果 agent 在运行过程中已经调用过构建（或之前的 trial 留下了缓存），verifier 的 UBT 会发现“没有变化”，直接返回成功。

### 影响

verifier 通过的 trial 中，可能实际代码并**不能真正编译通过**，只是被缓存掩盖了。这使得 pass rate 完全不可信。

---

## 2. Agent 崩溃但 Verifier 通过

### 现象

`uebuild-skillflow-20260614-5x-uebuild-t1`：
- `agent.exitCode = 1`
- `agent.failureClass = "agent-crash"`
- `verifier.passed = true`

### 根因

当前 runner 的通过判定只依赖 `verifier.passed`，没有将 `agent.exitCode` 纳入通过标准。agent 可能在崩溃前已经修改了文件，verifier 检查最终状态为“通过”，但 agent 实际上并未正常完成任务。

### 影响

benchmark 把“agent 崩溃但碰巧文件对了”算作通过，夸大了 agent 的稳定性。

---

## 3. 任务设计区分度不足

### 现象

`no-skills` 和 `ue-build-only` 两种条件下，都是 **5/5 通过（100%）**。delta = 0。

### 根因

`setup.ps1` 注入的损坏是：新增 `SkillsBenchNavProbe.cpp` 引用 `NavigationSystem` API，但 `TPSample.Build.cs` 缺少 `NavigationSystem` 依赖。

这个修复过于简单：
- 通用 agent 看到编译错误 `LNK2019` 或 `cannot open include file: NavigationSystem.h` 就能直接推断出要加模块依赖。
- 不需要 `ue-build` skill 中关于“如何解析 UBT 日志、如何确定正确 Target、如何使用 `-NoUBA` 避免偶发错误、如何区分 Launcher/Source-built 引擎”等知识。

### 影响

benchmark 没有测出 skill 的不可替代价值，只测了“agent 的通用 C++ 编译错误修复能力”。

---

## 4. Skill Usage 未观测到

### 现象

`ue-build-only` 条件下所有 trial 的 `skills.usageObserved = []`。

### 根因

Codex adapter 的 skill 注入方式是将 skill 文件复制到 `.codex/skills/`，但 Codex 的 skill 触发依赖 agent 自身在对话中识别到 skill 名称或描述并触发调用。对于简单的编译错误，Codex 直接靠自身知识修复，根本没有触发 `ue-build` skill 的 build 脚本。

### 影响

我们无法验证“通过率的提升（如果有的话）是否真的来自 skill 的使用”，而不是来自“多了一段 prompt 提示”。

---

## 5. 时间指标失真

### 现象

- `skillFlowSeconds` 和 `adapterWallSeconds` 差距巨大（如 `335.982` vs `1274.627`）。
- `wallClockSeconds` 也显著大于 `buildDurationSeconds`。

### 根因

- adapter 对 `durationSeconds` 和 `adapterWallSeconds` 的统计范围不一致：前者是 Codex `exec` 的子进程时间，后者包含了 prompt 输入准备和隔离环境创建。
- 没有区分“agent 思考时间”、“编译时间”和“IO/等待时间”。
- 构建时间因缓存被记录为 1 秒，没有任何参考价值。

---

## 修复方向

| 问题 | 修复措施 |
|------|---------|
| 缓存失真 | **Verifier 必须强制 Clean Build**：每次 verifier 运行前删除 `Intermediate/Binaries/Saved`，或使用 `-Rebuild` 参数；记录真实的编译耗时。 |
| 状态脱节 | **通过标准 = agent 正常退出 + verifier 通过**。agent crash 或 timeout 即使 verifier 通过也应标记为失败或单独分类。 |
| 任务区分度低 | **设计需要 skill 知识才能高效完成的损坏**：例如同时注入 UHT 反射错误 + 模块依赖错误 + 构建缓存污染，需要 `ue-build` skill 的“清理-重试-日志分析”工作流才能稳定修复。 |
| Usage 不可观测 | 当前 Codex 技能注入方式决定 usage 难以精确观测；短期内接受 `usageConfidence = partial`，但 pass/fail 必须以 verifier 为准。 |
| 时间失真 | 更细粒度的时间分段：setup / agent / clean-build / verification 分别计时。 |
| 通用性 | 用 Python 重写，支持插件化 task/verifier/adapter 注册，不硬编码 task 列表。 |

---

## 下一步

1. 用 Python 重写 runner 核心（config → workspace → adapter → verifier → report）。
2. 强制 verifier clean build 作为第一道防线。
3. 重新设计 `tps-build-repair` 任务，提升 skill 区分度。
4. 先跑通 `ue-build` 单一 skill 的 smoke + repair 任务，再扩展。

# Codex 真实 Agent 测试报告

## 测试环境

- Agent: OpenAI Codex CLI 0.139.0
- 模型: 默认（推测为 o3 或同代模型）
- 超时: 15 分钟（单模块）/ 20 分钟（多模块）
- 所有 trial 通过 verifier 强制 clean build（~46 秒）

---

## 结果汇总

### 单模块修复（tps-build-repair）

| 条件 | 通过 | Agent 耗时 | Wall Clock | Build 耗时 | 修复方式 |
|------|------|-----------|-----------|-----------|---------|
| no-skills | ✅ | 155.4s | 201.6s | 46.2s | 自己分析 LNK2019，添加到 Build.cs |
| ue-build-only | ✅ | 141.3s | 186.9s | 45.7s | 读取 SKILL.md，调用 build.ps1，分析日志，添加到 Build.cs |

**时间差异**: ue-build-only 快 **14.1s**（~9.1%），wall clock 快 **14.7s**（~7.3%）

### 多模块修复（tps-build-repair-multi）

| 条件 | 通过 | Agent 耗时 | Wall Clock | Build 耗时 | 修复方式 |
|------|------|-----------|-----------|-----------|---------|
| no-skills | ✅ | 150.9s | 196.7s | 45.7s | 自己分析 LNK2019，添加到 Build.cs |
| ue-build-only | ✅ | 138.5s | 184.1s | 45.7s | 读取 SKILL.md，调用 build.ps1，分析日志，添加到 Build.cs |

**时间差异**: ue-build-only 快 **12.5s**（~8.3%），wall clock 快 **12.5s**（~6.4%）

---

## 观察

### 1. 通过率

Codex 在 **no-skills 和 ue-build-only 两种条件下都 100% 通过**（4/4）。

这意味着：
- 当前任务（missing module dependency）对 Codex 而言属于**通用 C++ 编译错误修复能力**的范畴
- 不需要 `ue-build` skill 的 UE 特有知识（registry 解析、偶发错误重试、UBT 参数等）也能完成

### 2. Skill 使用情况

**ue-build-only 条件下，Codex 明确使用了 skill**：

1. 读取 `~/.codex/skills/ue-build/SKILL.md`
2. 调用 `build.ps1` 执行构建（而非自己直接调用 `Build.bat`）
3. 根据 SKILL.md 教的错误分类判断 linker error 属于编译错误（不重试）
4. 修复后再次调用 `build.ps1` 验证

**no-skills 条件下**，Codex 没有 skill 可用，但仍然：
- 自己调用 `Build.bat` 或类似的构建命令
- 分析 UBT 日志
- 定位到 `TPSample.Build.cs`
- 添加缺失模块

### 3. 修复策略差异

Oracle 把缺失模块加到 `PublicDependencyModuleNames`，Codex 加到 `PrivateDependencyModuleNames`。

因为 fixture 文件 `SkillsBenchBuildProbe.cpp` 位于 `Source/TPSample/`（同一模块内部），所以 `PrivateDependency` 也能编译通过。Codex 的选择实际上**更精确**（不需要 public 暴露）。

### 4. 时间差异

有 skill 时 Codex 快约 **8-9%**。原因可能是：
- skill 提供了现成的 `build.ps1` 脚本，Codex 不需要自己构造 UBT 命令行
- skill 提供了清晰的错误分类流程，减少了 agent 的推理步骤
- 但差异不大（~12-14 秒），因为任务本身简单

---

## 结论与下一步

### 当前任务区分度不足

两个条件的通过率都是 100%，delta = 0。这**不意味着 skill 没有价值**，而是：
- 当前任务难度（missing module dependency）是**通用编程能力**就能解决的
- 需要设计更难的 UE 特有任务，才能测出 skill 的不可替代性

### 建议的高区分度任务设计

1. **Intermediate 缓存污染**
   - setup 在 `Intermediate` 中注入一个过时的 `.generated.h` 或损坏的 `.obj`
   - 通用 agent 会反复尝试修改源代码，但构建仍然失败
   - 需要 `ue-build` skill 教的"清理 Intermediate 后重试"工作流

2. **偶发文件锁 + 多模块缺失**
   - 注入一个 setup 让首次 UBT 有概率报 "being used by another process"
   - 同时保留 module dependency 缺失
   - 通用 agent 看到文件锁可能放弃，或只修复 module 但运气不好再次遇到锁
   - 需要 skill 教的"最多重试 3 次"策略

3. **Launcher/Source-built 引擎混淆**
   - 修改 `.uproject` 的 `EngineAssociation` 为无效值
   - 需要 skill 教的"从 registry 解析引擎路径"知识

### 是否需要接入 ue-lsp / ue-autotest

由你决定。当前框架已支持：
- 添加新 task 到 `benchmarks/ue5-skillsbench/tasks/`
- 添加新 skill 到 `benchmarks/ue5-skillsbench/benchmark.yaml`
- 跑 `python -m runner run-single` 或 `run-matrix` 测试

如需接入，我可以设计：
- `ue-lsp`：测试代码补全/跳转到定义
- `ue-autotest`：测试自动化测试编写和运行

---

## 文件路径

- 单模块报告: `benchmarks/ue5-skillsbench/reports/codex-repair-summary.md`
- 多模块报告: `benchmarks/ue5-skillsbench/reports/codex-multi-summary.md`
- 运行产物:
  - `.bench/runs/codex-repair-001/` (no-skills)
  - `.bench/runs/codex-repair-002/` (ue-build-only)
  - `.bench/runs/codex-multi-001/` (no-skills, multi)
  - `.bench/runs/codex-multi-002/` (ue-build-only, multi)

# UE5 SkillsBench Python 重写 — 进度报告

## 已完成工作

### 1. 失真分析

已定位上一版 PowerShell 实现的 5 大失真根因，详见 `docs/ue5_skillsbench_analysis.md`：

- **Verifier 构建缓存失真**：UBT 增量编译导致 build duration 仅 ~1 秒，完全掩盖真实编译状态
- **Agent 状态与 Verifier 脱节**：agent crash 但 verifier 通过仍被算作 pass
- **任务区分度不足**：no-skills 条件也能 100% 通过，未测出 skill 不可替代价值
- **Skill usage 未观测**：Codex 未触发 skill 调用，无法验证增益来源
- **时间指标失真**：wall clock 与 agent duration 差距巨大，build time 无参考价值

### 2. 新设计文档

详见 `docs/ue5_skillsbench_python_design.md`，核心决策：

- **Verifier 强制 Clean Build**：每次 verifier 运行前删除 `Intermediate/Binaries`，确保真实编译
- **通过判定 = Agent 正常退出 + Verifier 通过**：agent crash 即使 verifier 通过也标记为失败
- **Python 重写**：支持插件化 task/verifier/adapter 注册，更通用
- **先跑通 ue-build**：暂时去掉 ue-lsp、ue-autotest，只保留 ue-build skill

### 3. Python Runner 核心框架

目录：`benchmarks/ue5-skillsbench/runner/`

| 模块 | 职责 |
|------|------|
| `config.py` | 解析 `benchmark.yaml`（支持 skill 路径映射）、扫描 `task.toml` |
| `preflight.py` | 环境检查：Windows、git、基线项目、UE 注册表、Build.bat/Editor-Cmd |
| `workspace.py` | 项目复制（排除生成目录）、git 初始化、skill 注入、安全边界 |
| `unreal.py` | 引擎路径解析（registry）、UBT 调用（支持 `clean=True` 强制重建）、UAT 调用 |
| `metrics.py` | git diff 统计（files changed、lines added/deleted） |
| `verifier.py` | 执行 verifier 脚本（支持 `.py` / `.ps1`），收集 `verifier_result.json` |
| `adapter.py` | `OracleAdapter`（应用 patch）、`NoopAdapter`（空操作）、`ManualAdapter`（人工） |
| `report.py` | JSON + Markdown 报告生成，含 pass rate、delta、normalized gain、失败分类 |
| `__main__.py` | CLI：`preflight`、`run-single`、`run-matrix`、`report` |

### 4. 任务实现

| 任务 | 说明 | 状态 |
|------|------|------|
| `tps-env-build-smoke` | 环境验证：clean build 基线项目，不计入 benchmark | ✅ 验证通过 |
| `tps-build-repair` | 构建修复：注入 `SkillsBenchBuildProbe.cpp` 引用 `NavigationSystem` + `GameplayTasks`，但 `Build.cs` 缺少两个依赖 | ✅ 验证通过 |

### 5. 验证结果

**Smoke test（clean build）**
- `build_duration_seconds = 46.652`（> 30 秒，证明非缓存）
- `overall_passed = true`

**Build repair oracle**
- `overall_passed = true`
- `build_duration_seconds = 47.339`（真实 clean build）
- `files_changed = 1, lines_added = 3, lines_deleted = 1`（与 oracle patch 一致）

**Build repair negative case（noop adapter，不修复）**
- `overall_passed = false`
- `failure_class = "build"`（verifier 正确检测到未修复的构建失败）

**报告生成**
- Markdown 表格正确汇总：task、condition、trials、pass rate、delta、build time、agent time、失败分类
- JSON 报告包含完整结构化数据

### 6. 关键修复点（对比上一版）

| 问题 | 上一版 | 新版 |
|------|--------|------|
| Build 缓存 | 未清理，duration ~1s | 强制 clean，duration ~46s |
| 通过判定 | 只看 verifier | Agent 正常 + verifier 通过 |
| Agent crash | 算作 pass | 算作 fail（failure_class） |
| 时间失真 | 无 clean build 区分 | 真实 build duration 记录 |
| 框架语言 | PowerShell 硬编码 | Python 插件化 task/adapter |
| Skill 注入 | 固定路径 `skills/ue-build` | `benchmark.yaml` 支持自定义路径映射 |

---

## 下一步建议

1. **接入真实 agent adapter**：接入 Codex CLI 或 Claude Code，跑 `no-skills` vs `ue-build-only` 的对比矩阵，收集真实 pass rate delta
2. **任务区分度提升**：当前 build-repair 任务（添加两个 module dependency）对通用 agent 仍可能 100% 通过。可设计更复杂的损坏（如 UHT 反射错误 + 缓存污染 + 特定 UBT 参数需求），需要 `ue-build` skill 的"日志分析-重试-清理"工作流才能稳定修复
3. **扩展 skill 覆盖**：补回 `ue-lsp` 和 `ue-autotest`，设计对应的 API 签名修复和自动化测试任务
4. **CI 集成**：将 `python -m runner preflight` 和 `run-matrix --adapter oracle` 加入 CI 作为回归测试

## 相关文件路径

- 分析文档：`docs/ue5_skillsbench_analysis.md`
- 设计文档：`docs/ue5_skillsbench_python_design.md`
- Python Runner：`benchmarks/ue5-skillsbench/runner/`
- 任务目录：`benchmarks/ue5-skillsbench/tasks/`
- 报告输出：`benchmarks/ue5-skillsbench/reports/`
- 运行产物：`.bench/runs/`

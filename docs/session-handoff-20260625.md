# UE5 SkillsBench Handoff — 2026-06-25 Session

**Author**: 当前会话
**Date**: 2026-06-25
**Commit**: `152d7d6`
**Status**: 框架已就绪，任务已实现，但 benchmark 结果可能有失真，需在干净环境中重新跑验证

---

## 本会话已完成的工作

### 1. 新增任务（2 个）

| 任务 | 文件 | 状态 |
|------|------|------|
| `tps-build-repair-cache-poisoned` | setup.py, verifier.py, oracle.patch, task.toml, instruction.md | 实现完毕，但缓存污染机制在 UE5 中**不生效**（UBT 不单纯依赖时间戳） |
| `tps-build-repair-transient-lock` | setup.py, verifier.py, oracle.patch, task.toml, instruction.md | 实现完毕，Oracle/Noop 验证通过，但 Kimi Code 区分度**待验证** |

### 2. Runner 框架改进

- `KimiCodeAdapter`: 新增，支持 `~/.kimi-code/bin/kimi.exe`（`-p` 非交互模式）
- `unreal.py`: 增强 `clean` 逻辑，支持 Windows 只读文件删除（`onexc=_remove_readonly`）
- `metrics.py`: 修复 `capture_git_diff` 编码问题（GBK → UTF-8）
- `__main__.py`: 注册 `kimi-code` adapter 选项

### 3. Benchmark 结果（**可能有失真**）

⚠️ **注意**：以下结果是在 runner 框架**持续修复中**（编码 bug、timeout 问题）同时跑出来的，可能存在失真。建议在干净环境中重新跑。

#### Kimi Code CLI（kimi-code adapter）

| 条件 | 通过率 | 备注 |
|------|--------|------|
| no-skills | 4/5 | t1 失败是 adapter 编码 bug（已修复），t2-t5 通过 |
| ue-build-only | 5/5 | t1-t4 通过，t5 runner timeout 但 workspace 验证通过 |

**关键发现**：
- no-skills 下 Kimi Code 也能通过（自动清理 Binaries + 修复 Build.cs）
- **ue-build-only t3 异常**：改了 5 个文件（+118 行），可能调用了 skill 中的 `.ps1` 脚本，但日志已清理，无法确认
- 当前任务**区分度不明确**，需重新验证

---

## 核心问题

### 任务区分度是否为零？

**当前结论（待验证）**：
- `tps-build-repair-transient-lock` 的 LNK1104 错误 + Build.cs 修复，通用 LLM 常识已足以解决
- ue-build-only t3 的异常文件修改数（5 files, +118 lines）暗示可能使用了 skill，但无日志确认

**需要在新会话中验证**：
1. 重新跑 3 次 no-skills（观察是否都通过）
2. 重新跑 3 次 ue-build-only（观察 agent 行为，确认是否调用 skill 脚本）
3. 对比两者的**修复路径**（是否不同）和**最终通过率**

---

## 新会话的执行清单

### Step 1: 确保环境干净

```bash
# 清理旧的测试目录
rm -rf .bench/runs
```

### Step 2: 跑 3 次 no-skills

```bash
cd benchmarks/ue5-skillsbench
python -m runner run-single \
  --task-id tps-build-repair-transient-lock \
  --condition no-skills \
  --adapter kimi-code \
  --trial 1 \
  --skip-preflight \
  --timeout-minutes 45 \
  --verifier-timeout 30

# 重复 t2, t3
```

### Step 3: 跑 3 次 ue-build-only

```bash
python -m runner run-single \
  --task-id tps-build-repair-transient-lock \
  --condition ue-build-only \
  --adapter kimi-code \
  --trial 1 \
  --skip-preflight \
  --timeout-minutes 45 \
  --verifier-timeout 30

# 重复 t2, t3
```

### Step 4: 检查 agent 行为

每次跑完后检查：
```bash
# 查看 agent 是否调用了 skill 脚本
cat .bench/runs/<run-id>/artifacts/agent.stdout.log | grep -i "skill\|ps1\|script\|clean"

# 查看 git diff 统计
cd .bench/runs/<run-id>/workspace/TPSample
git diff --stat
```

**特别关注**：
- ue-build-only 下是否调用了 `skills/ue-build/` 目录下的 `.ps1` 脚本
- no-skills 和 ue-build-only 的修复路径是否不同

### Step 5: 对比结论

| 对比项 | no-skills | ue-build-only | 是否有差异 |
|--------|-----------|-----------------|-----------|
| 通过率 | ? | ? | 关键指标 |
| 是否调用 skill 脚本 | N/A | ? | 验证核心 |
| 修复路径 | ? | ? | 观察行为差异 |
| 平均耗时 | ? | ? | 辅助指标 |

---

## 已知问题

1. **Bash timeout 300s**：kimi CLI 在 ue-build-only 下可能超时（因为需要加载 skill 文件），如超时需手动验证 workspace 或延长 timeout
2. **KimiCodeAdapter 已修复**：`-p` 与 `--yolo`/`--auto` 冲突已解决，当前使用 `[kimi, "--output-format", "text", "-p", prompt]`
3. **verifier 的 clean build**：会自动删除 `Binaries/` 和 `Intermediate/`，所以即使 agent 没清理，verifier 也会清理

---

## 相关文件路径

- 任务定义：`benchmarks/ue5-skillsbench/tasks/tps-build-repair-transient-lock/`
- Runner 框架：`benchmarks/ue5-skillsbench/runner/`
- 报告：`docs/ue-build-benchmark-conclusion.md`
- 上一版交接：`docs/ue5_skillsbench_handoff.md`
- 结论报告：`docs/ue-build-benchmark-conclusion.md`

---

## 任务目标（不变）

验证 `ue-build` skill 的不可替代价值：
- 如果 no-skills 和 ue-build-only 的通过率/行为**有显著差异** → 任务有价值，继续
- 如果**无差异** → 任务需要重新设计（参考 `docs/ue-build-benchmark-conclusion.md` 中的方案 B/C）


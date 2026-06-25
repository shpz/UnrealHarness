# UE5 SkillsBench Handoff — 高区分度任务实现计划

**文档日期**: 2026-06-25  
**当前状态**: Python runner 已跑通，5 个基础任务（smoke + build-repair + multi + engine-typo + uht）已验证，Codex adapter 已接入。  
**目标**: 实现并跑通 **建议 1（缓存污染）** 和 **建议 3（偶发文件锁）**，测出 ue-build skill 的不可替代价值。

---

## 背景：为什么需要这两个任务

当前所有 build-repair 任务（missing module dependency）对 Codex 都属于**通用 C++ 编译错误修复**范畴：
- `no-skills` 和 `ue-build-only` 通过率都是 **100%**
- 有 skill 时只快约 **8–12%**（时间差异）
- 没有测出 `ue-build` skill 的**不可替代价值**（registry 解析、缓存清理、偶发错误重试等工作流知识）

**建议 1 和 3 的设计目标**：让通用 agent 陷入死循环或误判，只有使用 `ue-build` skill 的"清理-重试"工作流才能稳定通过。

---

## 建议 1：Intermediate 缓存污染（tps-build-repair-cache-poisoned）

### 核心机制

UBT 的增量编译依赖文件时间戳。如果 `Intermediate/` 下预生成的 `.obj` 比修改后的 `.cpp`/`.Build.cs` **更新**，UBT 会跳过编译该文件，直接复用旧 `.obj`。即使 agent 正确修复了 Build.cs，链接阶段仍报 `LNK2019`（未解析符号），因为旧 `.obj` 没有包含新模块的符号。

通用 agent 的典型失败模式：
1. 看到 `LNK2019` → 分析日志 → 发现缺少 module → 修改 Build.cs
2. 重新构建 → 仍然 `LNK2019` → 以为自己修改错了 → 反复调整 Build.cs
3. 陷入死循环，无法意识到是**缓存时间戳问题**

`ue-build` skill 的修复知识：遇到 linker error 且已确认修改正确 → 执行 "清理 Intermediate 后重试"。

### 实现步骤

1. **创建目录**
   ```
   benchmarks/ue5-skillsbench/tasks/tps-build-repair-cache-poisoned/
   ```

2. **setup.py**（核心逻辑）

   在注入 `SkillsBenchBuildProbe.cpp`（引用 `NavigationSystem` + `GameplayTasks`，Build.cs 不添加依赖）之后，**额外执行**：
   
   a. 先触发一次真实的 UBT 构建（会失败，但会生成 `.obj`）  
   b. 找到 `Intermediate/Build/Win64/x64/.../Module.TPSample.*.cpp.obj`  
   c. 修改该 `.obj` 的时间戳为**未来时间**（如 `datetime.now() + 1 day`）  
   d. 这样即使 agent 后来修改 Build.cs，UBT 仍认为 `.obj` 是最新的，跳过编译

   ```python
   # setup.py 关键逻辑示意
   import subprocess, time
   from pathlib import Path
   
   # 1. 注入 fixture
   # ...（同 tps-build-repair）
   
   # 2. 触发一次真实构建（会失败但生成 .obj）
   subprocess.run([build_bat, "TPSampleEditor", "Win64", "Development", uproject], ...)
   
   # 3. 找到 .obj 并修改时间戳为未来
   obj_pattern = project_path / "Intermediate" / "Build" / "Win64" / "x64" / "UnrealEditor" / "Development" / "TPSample" / "Module.TPSample*.cpp.obj"
   for obj in obj_pattern.parent.glob(obj_pattern.name):
       future_time = time.time() + 86400  # 1 day later
       os.utime(obj, (future_time, future_time))
   ```

3. **verifier.py**
   - 强制 `clean=True`（会删除 `Intermediate`），所以 verifier 自身不受缓存污染影响
   - 检查 fixture 未被删除、Build.cs 有正确模块、build 通过

4. **oracle.patch**
   - 包含两部分：修改 Build.cs 添加缺失模块 + 清理 `Intermediate/` 目录
   - 或者 oracle 只做 `git apply patch`（只改 Build.cs），然后 verifier 的 clean build 自动清理 Intermediate

   **建议**：oracle.patch 只包含 Build.cs 的修改，verifier 的 clean build 会自动解决缓存问题。这样 oracle 更简洁。

5. **benchmark.yaml 条件**
   - 和现有任务一样，支持 `no-skills` vs `ue-build-only`

### 预期 Codex 行为对比

| 条件 | 预期行为 | 预期结果 |
|------|---------|---------|
| no-skills | Codex 修改 Build.cs → 重新 build → 仍 LNK2019 → 反复修改 → 超时或放弃 | ❌ 失败或极慢 |
| ue-build-only | Codex 读取 SKILL.md → 看到"偶发/缓存问题 → 清理 Intermediate 后重试"→ 清理后 rebuild → 通过 | ✅ 通过 |

### 验证方式

```bash
# 先跑 oracle 确保框架正确
python -m runner run-single --task-id tps-build-repair-cache-poisoned --condition no-skills --adapter oracle --trial 1

# 再跑 Codex 对比
python -m runner run-single --task-id tps-build-repair-cache-poisoned --condition no-skills --adapter codex --trial 1 --timeout-minutes 20
python -m runner run-single --task-id tps-build-repair-cache-poisoned --condition ue-build-only --adapter codex --trial 1 --timeout-minutes 20
```

---

## 建议 3：偶发文件锁 + 多模块缺失（tps-build-repair-transient-lock）

### 核心机制

UE5 的 `Build.bat` 在 Windows 上偶尔会遇到 `.dll` 被其他进程占用（如编辑器正在运行、Windows Search 索引、杀毒软件），报类似错误：
```
The process cannot access the file because it is being used by another process
```

`ue-build` skill 的 `SKILL.md` 明确教了：遇到 "cannot access" / "being used by another process" → 偶发性错误 → **重试（最多 3 次）**。而通用 agent 没有这种知识，看到文件锁可能直接放弃或报告无法修复。

### 设计思路：模拟文件锁

Windows 上真实模拟文件锁比较复杂。一种更可控的替代方案：

**setup.py 让第一次 UBT 构建有概率/必定失败（非缓存问题）**：
- 在 `Binaries/Win64/` 下预先放置一个同名 `.dll` 并设为**只读**
- 或者通过环境变量/脚本让 `Build.bat` 首次调用时注入一个特定的 stderr 错误

更简单的方案：
- **setup 不注入文件锁，而是直接在 setup 中触发一次 UBT 构建**
- 这次构建会失败（因为 module 缺失），但会在 `Binaries/Win64/` 留下一个**不完整的 `.dll`** 或 `.lib`
- 如果 agent 的构建命令和 setup 的构建命令并发，Windows 可能报文件锁
- 但并发控制困难，不稳定

**更稳定的方案：setup 中注入一个虚假的 UBT 错误模式**

在 `setup.py` 中，不真正调用 UBT，而是写一个假的 `.lastbuild` 或修改环境让 agent 在构建时看到特定错误。但这过于 hacky，不太可靠。

**推荐方案：利用 Windows 文件锁的真实场景**

1. setup.py 注入 fixture + 缺失 module
2. setup.py 调用一次 `Build.bat`（会失败）
3. 在 `Binaries/Win64/` 下找到生成的部分文件（如 `.dll`、`.lib`）
4. 启动一个**后台进程**打开这些文件并持有句柄（不释放）
5. 这样 agent 后续调用 `Build.bat` 时，链接器无法写入这些文件，报 "being used by another process"
6. agent 需要关闭后台进程或重试

但这样 verifier 也会遇到同样问题（因为 verifier 也调用 build）。所以需要：
- 在 verifier 的 `clean=True` 模式下，先删除 `Binaries/`，同时释放锁
- 或者 setup.py 在完成后清理后台进程

**更简化的替代方案：setup 直接注入一个 powershell 脚本，让 agent 的第一次构建必定报锁错误**

在 `setup.py` 中：
- 创建一个自定义的 `.bat` 或环境变量，劫持 `Build.bat` 的首次调用
- 但这过于侵入，不推荐

**最终推荐方案：利用 UBT 本身的并行构建偶发错误**

实际上，UBT 在 `UnrealBuildTool` 的并行链接阶段，偶尔会因为 `.dll` 被 Windows Defender 扫描而报锁。这不是稳定可复现的。

**最实际的方案：setup.py 中预创建一个只读的空 `.dll` 文件**

```python
# setup.py 关键逻辑
binaries_dir = project_path / "Binaries" / "Win64"
binaries_dir.mkdir(parents=True, exist_ok=True)
stub_dll = binaries_dir / "UnrealEditor-TPSample.dll"
stub_dll.write_bytes(b"")  # 空文件
# 设为只读
os.chmod(stub_dll, 0o444)
```

但这样 agent 调用 `Build.bat` 时，链接器可能报 "cannot write to file" 或 "access denied"，而不一定是 "being used by another process"。

**建议：保留任务设计，但实现方式灵活调整**

任务目录先创建，setup.py 可以先实现最简版本（预生成过时 `.obj` 或空只读 `.dll`），跑通后观察 Codex 的反应。如果实际报错和预期不同，再调整 setup 逻辑。

### 实现步骤（最简版）

1. **创建目录**
   ```
   benchmarks/ue5-skillsbench/tasks/tps-build-repair-transient-lock/
   ```

2. **setup.py（最简版）**
   - 注入 `SkillsBenchBuildProbe.cpp`（多模块缺失）
   - 额外在 `Binaries/Win64/` 下创建一个**只读**的空 `UnrealEditor-TPSample.dll`
   - 这样链接阶段会报写入错误，agent 需要识别这是"偶发/环境问题"而非"代码错误"

3. **verifier.py**
   - 强制 `clean=True`（先删除 `Binaries/`，移除只读文件）
   - 然后正常 clean build

4. **oracle.patch**
   - 修改 Build.cs 添加缺失模块
   - 同时删除/覆盖 `Binaries/Win64/UnrealEditor-TPSample.dll`（从只读恢复）

5. **预期 Codex 行为对比**

   | 条件 | 预期行为 | 预期结果 |
   |------|---------|---------|
   | no-skills | 看到 "access denied" 或 "cannot write" → 可能误判为权限问题 → 尝试修复权限但无果 → 失败 | ❌ 失败 |
   | ue-build-only | 读取 SKILL.md → 看到"cannot access → 重试 3 次" → 重试前可能清理 Binaries → 通过 | ✅ 通过 |

### 验证方式

```bash
python -m runner run-single --task-id tps-build-repair-transient-lock --condition no-skills --adapter oracle --trial 1
python -m runner run-single --task-id tps-build-repair-transient-lock --condition no-skills --adapter codex --trial 1 --timeout-minutes 20
python -m runner run-single --task-id tps-build-repair-transient-lock --condition ue-build-only --adapter codex --trial 1 --timeout-minutes 20
```

---

## 优先级与实施顺序

| 优先级 | 任务 | 原因 | 预估工作量 |
|--------|------|------|-----------|
| **P0** | 建议 1（缓存污染） | 机制清晰，稳定可控，最容易复现 | 2–3 小时 |
| **P1** | 建议 3（文件锁） | Windows 文件锁模拟有不确定性，需要调试 | 3–4 小时 |

**建议先实现 P0（缓存污染）**，跑通并验证 Codex 在 `no-skills` 下确实失败/超时，再处理 P1。

---

## 当前已有资源

- `runner/` 框架完整，支持 `oracle` / `noop` / `manual` / `codex` adapter
- `unreal.py` 的 `invoke_build(clean=True)` 自动删除 `Intermediate/Binaries`
- `setup.py` 可以执行任意 Python 逻辑（包括修改文件时间戳、调用 UBT）
- `verifier.py` 可以检查 fixture 存在性、Build.cs 内容、clean build 通过
- `.bench/runs/` 产物保留完整，便于事后分析 agent 的决策路径

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| Codex 在 no-skills 下也碰巧清理了 Intermediate（通用搜索） | 观察 agent.stdout.log，确认是否显式清理了目录；如果发生，说明任务区分度仍不足，需要更隐蔽的缓存注入 |
| 文件锁模拟不稳定（Windows 版本差异） | 使用最简版（只读空 .dll），如果不行再换其他方案 |
| setup.py 调用 UBT 耗时太长（先 build 再改时间戳） | setup.py 的 timeout 在 `task.toml` 中设置，`timeout_minutes = 45` 应该足够 |
| 多任务并行时 .bench/runs/ 冲突 | 每次 `run-single` 的 `--run-id` 唯一，不会冲突 |

---

## 交接人 Checklist

- [ ] 实现 `tps-build-repair-cache-poisoned` 的 `setup.py` / `verifier.py` / `oracle.patch` / `task.toml` / `instruction.md`
- [ ] 跑 oracle adapter 验证框架正确（`overall_passed = true`）
- [ ] 跑 noop adapter 验证 negative case（`overall_passed = false`）
- [ ] 跑 Codex `no-skills` 和 `ue-build-only` 各 1–3 trial，观察 delta
- [ ] 如果 P0 成功，继续实现 P1（文件锁）
- [ ] 更新 `benchmark.yaml` 注册新任务（如果需要）
- [ ] 提交 `git commit` 并 push

---

## 相关文件路径

- 框架：`benchmarks/ue5-skillsbench/runner/`
- 现有任务参考：`benchmarks/ue5-skillsbench/tasks/tps-build-repair/`、`tps-build-repair-multi/`
- 报告：`benchmarks/ue5-skillsbench/reports/`
- 运行产物：`.bench/runs/<run-id>/`
- 文档：`docs/ue5_skillsbench_codex_results.md`（上一版测试结果）

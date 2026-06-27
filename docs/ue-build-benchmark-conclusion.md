# UE-Build Skill Benchmark 结论报告

**任务**: `tps-build-repair-transient-lock`（文件锁 + 多模块缺失）
**日期**: 2026-06-25
**Commit**: `1e9dcd8`

---

## 1. 任务设计

### 1.1 核心机制

在 `Binaries/Win64/` 下预创建一个 **只读空 DLL** (`UnrealEditor-TPSample.dll`)，同时注入引用 `NavigationSystem` + `GameplayTasks` 模块的 fixture 代码（但 `Build.cs` 不声明这两个模块）。

Agent 构建时的典型链路：
1. 编译通过 → 链接阶段失败（`LNK1104`: 无法写入只读 .dll）
2. 或者编译直接报错（因为 `Build.cs` 缺少模块）

### 1.2 修复路径

- **必须修改**: `Source/TPSample/TPSample.Build.cs` → 添加 `"NavigationSystem"` 和 `"GameplayTasks"`
- **必须清理**: 删除 `Binaries/` 下的只读 .dll（否则链接器仍无法写入）
- **verifier 用 clean build** 自动清理，所以只改 Build.cs 即可通过 oracle

---

## 2. 实验结果

### 2.1 Kimi Code CLI（kimi-code adapter）

| 条件 | 通过 | 失败 | 平均 Agent 时间 | 平均 Build 时间 |
|------|------|------|----------------|----------------|
| **no-skills** | 4/5 | 1/5 | ~160s | ~47s |
| **ue-build-only** | 5/5 | 0/5 | ~200s | ~47s |

*注：no-skills t1 的 1 次失败是 KimiCodeAdapter 参数编码 bug（`--yolo` 与 `-p` 冲突），修复后 t2-t5 全部通过。*

### 2.2 关键发现

**任务区分度 ≈ 0**

Kimi Code 在 **no-skills** 条件下同样能稳定通过：
- 自动识别 `LNK1104` 链接错误
- 自动清理 `Binaries/` 和 `Intermediate/`
- 正确解析 `Build.cs` 缺失模块
- 最终 clean build 通过

这说明当前任务的设计目标——"让通用 agent 陷入死循环，只有 ue-build skill 才能通过"——**没有实现**。

### 2.3 与交接文档预期的对比

| 预期 | 实际 | 偏差原因 |
|------|------|---------|
| no-skills 反复修改 Build.cs 后仍 LNK1104 → 失败 | no-skills 清理 Binaries 后一次通过 | Kimi Code 的通用常识已包含"清理输出目录后重试" |
| ue-build-only 读取 SKILL.md 后按"清理-重试"工作流通过 | 确实通过，但 no-skills 也能通过 | 该工作流不是 skill 专属知识 |

---

## 3. 已完成的工程改进

### 3.1 新增任务

| 任务 | 文件 | 状态 |
|------|------|------|
| `tps-build-repair-cache-poisoned` | setup.py, verifier.py, oracle.patch, task.toml, instruction.md | 已实现，但缓存污染机制在 UE5 中不生效（UBT 不单纯依赖时间戳） |
| `tps-build-repair-transient-lock` | setup.py, verifier.py, oracle.patch, task.toml, instruction.md | 已实现，验证通过，但区分度不足 |

### 3.2 Runner 框架改进

- `KimiCodeAdapter`: 新增，支持 `~/.kimi-code/bin/kimi.exe` 调用
- `unreal.py`: 增强 `clean` 逻辑，支持 Windows 只读文件删除（`onexc=_remove_readonly`）
- `metrics.py`: 修复 `capture_git_diff` 编码问题（GBK → UTF-8）
- `__main__.py`: 注册 `kimi-code` adapter 选项

### 3.3 已提交的文件

```
benchmarks/ue5-skillsbench/runner/adapter.py        (+ KimiCodeAdapter)
benchmarks/ue5-skillsbench/runner/__main__.py       (+ kimi-code option)
benchmarks/ue5-skillsbench/runner/metrics.py        (encoding fix)
benchmarks/ue5-skillsbench/runner/unreal.py         (read-only cleanup)
benchmarks/ue5-skillsbench/tasks/tps-build-repair-cache-poisoned/     (new)
benchmarks/ue5-skillsbench/tasks/tps-build-repair-transient-lock/     (new)
docs/ue5_skillsbench_handoff.md                      (new)
prepare_trials.py                                    (new, helper script)
```

---

## 4. 为什么当前设计没有高区分度

### 4.1 根本原因：LNK1104 是"通用可修复错误"

当 agent 看到：
```
LINK : fatal error LNK1104: 无法打开文件 ...\UnrealEditor-TPSample.dll
```

通用 LLM 的修复知识：
1. 文件被占用/只读 → 删除或释放
2. 删除后重试

这不是 UE5 特有的知识，不需要 `ue-build` skill。

### 4.2 对比现有任务的区分度

| 现有任务 | 通用 agent 失败点 | 区分度 |
|---------|-----------------|--------|
| `tps-build-repair`（简单缺失模块） | 无，Codex 100% 通过 | 低 |
| `tps-build-repair-multi`（多模块缺失） | 无，Codex 100% 通过 | 低 |
| `tps-build-repair-engine-typo` | 无，Codex 100% 通过 | 低 |
| `tps-build-repair-uht` | 无 | 低 |
| `tps-build-repair-transient-lock`（本任务） | **无**（Kimi Code 清理后通过） | **低** |

---

## 5. 下一步：如何实现高区分度

### 5.1 方案 A：UHT 缓存污染（更隐蔽）

在 `setup.py` 中：
1. 先生成正确的 `generated.h` 和 `.cpp`（通过 UHT）
2. 修改 `generated.h` 中的某个函数签名（与未来 fixture 需要的签名不一致）
3. 这样 agent 修复 `Build.cs` 后，UHT 不会重新运行（因为 `.h` 的时间戳比 `.Build.cs` 新）
4. 链接时产生不匹配错误，agent 无法通过清理解决（因为 UHT 不重新生成）

**挑战**：需要深入 UHT 的增量逻辑，确保时间戳/依赖检测不会触发重新生成。

### 5.2 方案 B：并发文件锁（真实不可清理）

在 `setup.py` 中：
1. 启动一个后台进程，用 `CreateFile` + `FILE_SHARE_NONE` 锁定 `Binaries/Win64/UnrealEditor-TPSample.dll`
2. 这个锁在 verifier 运行前不会释放
3. agent 无法通过删除文件来解除锁（因为进程持有句柄）
4. 只有 `ue-build` skill 知道"需要找到占用进程并终止它"

**挑战**：需要跨进程控制（setup.py 启动进程 → verifier 终止进程），增加了框架复杂度。

### 5.3 方案 C：Build.cs 配置陷阱（非模块缺失）

设计一个 Build.cs 的错误不是"缺少模块"，而是更隐蔽的：
- 错误的 `PublicIncludePaths`
- 错误的 `PrivateDependencyModuleNames`（模块存在但访问权限错误）
- 预编译头（PCH）配置冲突

让通用 agent 误判为"代码错误"而非"配置错误"。

### 5.4 方案 D：环境变量/注册表注入

在 `setup.py` 中修改环境变量或注册表项，使 UBT 的某些路径解析错误。只有 `ue-build` skill 知道需要检查环境变量。

**挑战**：过于 hacky，可能不稳定。

---

## 6. 建议优先级

| 优先级 | 方案 | 预估工作量 | 区分度潜力 |
|--------|------|-----------|-----------|
| P0 | 方案 B（真实文件锁 + 后台进程） | 3-4 小时 | 高（需特定技能解除） |
| P1 | 方案 A（UHT 缓存污染） | 4-5 小时 | 中高（需理解 UHT 增量机制） |
| P2 | 方案 C（Build.cs 配置陷阱） | 2-3 小时 | 中（取决于陷阱设计） |
| P3 | 方案 D（环境变量注入） | 2 小时 | 低-中（过于 hacky） |

---

## 7. 结论

1. **P1（文件锁任务）已实现并验证**：Oracle 通过、Noop 失败、Kimi Code 通过（no-skills 和 ue-build-only 都通过）。
2. **任务区分度不足**：通用 LLM（Kimi Code）的常识已足以解决 LNK1104 + Build.cs 修复问题。
3. **需要重新设计**任务机制，让通用 agent 无法通过"清理 + 重试"的常识解决。
4. **推荐下一步**：实现方案 B（真实文件锁 + 后台进程），或者深入分析 UHT 的增量机制实现方案 A。
5. **Runner 框架已升级**：支持 Kimi Code CLI、Windows 只读文件清理、编码修复。

---

*Generated: 2026-06-25*

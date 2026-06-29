# UE-Build Skill Benchmark 结论报告

**日期**: 2026-06-27

---

## 1. `ue-build` 的实际作用

`ue-build` 是一个**纯编译命令包装器**，核心价值：

| 能力 | build.py 实现 | SKILL.md 指导 |
|------|---------------|---------------|
| **自动项目发现** | 当前目录搜索 `*.uproject`，单个自动使用，多个列出选择 | 检查当前目录 → 自动使用或提示指定 |
| **引擎路径解析** | 从 `.uproject` 的 `EngineAssociation` 读取注册表（Launcher 版本号 / GUID） | 自动处理，无需手动 |
| **Target 推导** | `项目名 + Editor` | 自动推导 |
| **偶发性错误重试** | 返回 exit code，不重试 | Agent 层遇到 `cannot access` / `being used by another process` 时重试 3 次 |

**明确不做的事情**：
- ❌ 不修改任何源代码（SKILL.md 第 9 行）
- ❌ 不修复编译错误（`error C`、`error LNK` → 直接报告，不重试）
- ❌ 不清理 `Binaries/` / `Intermediate/`
- ❌ 不诊断 UHT 缓存问题
- ❌ 不终止占用进程

---

## 2. 任务列表

| 任务 | 类型 | 说明 |
|------|------|------|
| `tps-env-build-smoke` | 基准测试 | 环境检查，确保项目能编译 |
| `tps-build-auto-discover` | `ue-build` 核心能力 | 自动项目发现（多层目录） |
| `tps-build-engine-resolve` | `ue-build` 核心能力 | GUID 注册表引擎路径解析 |

---

## 3. 任务设计说明

### 3.1 `tps-build-auto-discover`（多层目录自动发现）

**设计**：
- `setup.py` 将项目文件移动到 `Projects/GameA/` 子目录，同时在 `Projects/GameB/` 创建空壳诱饵项目
- `verifier.py` 搜索子目录，找到正确的 `GameA/TPSample.uproject` 并编译

**区分度逻辑**：
- `ue-build` 的 `build.py` 的 `find_project_file` 只搜索当前目录（不递归），所以 agent 必须显式指定 `--project` 参数
- 有 `ue-build` 的 agent：SKILL.md 指导它"检查当前目录 → 未找到 → 询问/指定路径"，然后 `--project Projects/GameA/TPSample.uproject`
- 无 `ue-build` 的 agent：需要自行发现项目位置，然后手动构造 Build.bat 命令，步骤更多

**验证标准**：`TPSampleEditor` 编译成功。

### 3.2 `tps-build-engine-resolve`（GUID 注册表解析）

**设计**：
- `setup.py` 将 `.uproject` 的 `EngineAssociation` 从 Launcher 版本号（如 `"5.7"`）改为 GUID
- 在 `HKCU\SOFTWARE\Epic Games\Unreal Engine\Builds\{GUID}` 注册表项中写入正确的引擎路径

**区分度逻辑**：
- `ue-build` 的 `build.py` 自动识别 GUID 格式，从 `HKCU` 注册表解析引擎路径，一步完成编译
- 无 `ue-build` 的 agent：需要知道源码编译引擎的注册表路径（`HKCU\...\Builds\{GUID}`），而不是 Launcher 版本的路径（`HKLM\SOFTWARE\EpicGames\...`），然后手动构造命令

**验证标准**：`TPSampleEditor` 编译成功，且引擎路径正确解析。

---

*Updated: 2026-06-27*

# UE5 SkillsBench Python 重写设计

## 设计目标

1. **修复结果失真**：verifier 强制 clean build，agent 状态与 verifier 结果联合判定 pass/fail。
2. **更通用**：不硬编码 task 列表，支持通过目录约定自动发现 task、verifier、adapter。
3. **先跑通 ue-build**：暂时去掉 ue-lsp、ue-autotest，只保留 ue-build skill 做 MVP。
4. **Python 重写**：利用 Python 的跨平台生态、YAML/TOML 解析库、subprocess 管理能力，替代上一版 PowerShell 实现。

---

## 目录结构

```
benchmarks/ue5-skillsbench/
├── benchmark.yaml              # 全局配置（沿用上一版，但简化 conditions）
├── runner/
│   ├── __init__.py
│   ├── __main__.py             # python -m runner 入口
│   ├── config.py               # 解析 benchmark.yaml，返回 dataclass
│   ├── preflight.py            # 环境检查：PS>=5.1, git, 基线项目, UE 注册表, Build.bat, Editor-Cmd
│   ├── workspace.py            # 项目复制、git 初始化、skill 注入、安全边界检查
│   ├── unreal.py               # 引擎路径解析（registry）、UBT/UAT 调用（支持 clean/rebuild）
│   ├── verifier.py             # 执行 verifier 脚本（支持 .py/.ps1）、结果收集、强制 clean 标志
│   ├── adapter.py              # Adapter 抽象基类
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── oracle.py           # 应用 oracle.patch
│   │   └── manual.py           # 暂停等待人工干预
│   ├── metrics.py              # git diff 统计（files changed, lines added/deleted）
│   └── report.py               # JSON + Markdown 报告生成
├── tasks/
│   ├── tps-env-build-smoke/    # 环境验证任务（不计入 benchmark）
│   │   ├── instruction.md
│   │   ├── task.toml
│   │   ├── setup.py            # 空 setup，或仅验证基线项目存在
│   │   └── verifier.py         # 强制 clean build 基线项目
│   └── tps-build-repair/       # 构建修复任务（区分度更高的设计）
│       ├── instruction.md
│       ├── task.toml
│       ├── setup.py            # 注入需要 ue-build 知识才能修复的损坏
│       ├── oracle.patch
│       └── verifier.py         # 强制 clean build + 静态检查
└── reports/                    # 运行报告输出目录
```

运行产物目录沿用 `.bench/runs/<run-id>/`（不进入版本管理）：

```
.bench/runs/<run-id>/
├── <task-id>/<condition>/trial-<n>/
│   ├── workspace/
│   │   ├── TPSample/           # 项目副本（含 .git）
│   │   ├── instruction.md      # 任务说明
│   │   └── skills/             # 仅 skills 条件存在
│   ├── artifacts/
│   │   ├── setup.stdout.log
│   │   ├── setup.stderr.log
│   │   ├── agent.stdout.log
│   │   ├── agent.stderr.log
│   │   ├── git.diff
│   │   ├── build.log           # verifier 构建日志
│   │   ├── verifier_result.json
│   │   └── verifier.stdout.log
│   └── result.json             # 结构化结果
```

---

## 关键设计决策

### 1. 强制 Clean Build

`unreal.py` 的 `invoke_build` 函数增加 `clean: bool = False` 参数。

- 当 `clean=True` 时，先删除目标项目的 `Intermediate` 和 `Binaries` 目录，再调用 `Build.bat`。
- 对于 Development Editor 构建，这是安全且足够的（不需要清理全局 Engine DDC）。
- `verifier.py` 对所有 UE 构建相关任务默认使用 `clean=True`。

### 2. 通过判定 = Agent 正常退出 + Verifier 通过

`result.json` 中：

```json
{
  "verifier": { "passed": true, "exitCode": 0 },
  "agent": { "exitCode": 0, "timedOut": false },
  "overallPassed": true
}
```

- `overallPassed = (agent.exitCode == 0 && !agent.timedOut && verifier.passed)`
- 如果 agent crash 但 verifier 通过，记录为 `failureClass: "agent-crash"`，`overallPassed: false`。
- 如果 agent 正常但 verifier 失败，记录为 `failureClass` 从 verifier 继承（如 `build`）。

### 3. 任务设计提升区分度

`tps-build-repair` 的新 setup 不再只是“缺少一个 module dependency”。而是注入一个**需要 `ue-build` skill 工作流知识**才能稳定修复的损坏：

**损坏设计：缓存污染 + 模块依赖 + 反射错误**

1. `setup.py` 注入 `Source/TPSample/SkillsBenchBuildProbe.cpp`，引用 `AIModule` 的 `UAISystem` API。
2. 同时故意修改 `TPSample.Build.cs`，把 `AIModule` 从 `PublicDependencyModuleNames` 移到错误的 `PrivateDependencyModuleNames` 中（或者干脆删掉）。
3. 再注入一个 `UCLASS()` 缺少 `Blueprintable` 的错误（但这会导致 UHT 失败，可能过于复杂）。

更简单的方案：
- 注入的 `.cpp` 文件使用 `NavigationSystem` 和 `GameplayTasks` 两个模块 API。
- `Build.cs` 只保留 `NavigationSystem`，缺少 `GameplayTasks`。
- 同时在 `Intermediate` 里预放一个**过时的 `.generated.h`** 或手动篡改一个 `.cpp` 的 include，让首次构建的 UBT 日志非常混乱。
- 但 `setup.py` 不应该直接改 `Intermediate`（会被 copy exclude 排除）。

**MVP 折中方案**：
- 注入多模块依赖缺失（至少 2 个不常见的 UE 模块）。
- 让 `verifier` 做 clean build，确保没有缓存。
- 这样即使通用 agent 能修，也需要解析更复杂的 UBT 日志，耗时和稳定性上会有差异；但 pass rate 仍可能接近。这是第一阶段可接受的——先保证框架正确，再逐步提升任务难度。

### 4. 通用 Task 发现机制

`config.py` 扫描 `tasks/` 目录，每个子目录必须包含 `task.toml` 和 `verifier.py`（或 `verifier.ps1`）。

```toml
id = "tps-build-repair"
project = "TPSample"
timeout_minutes = 45
primary_skills = ["ue-build"]

[metadata]
difficulty = "medium"
category = "software-engineering"
subcategory = "build-repair"
```

runner 读取 `benchmark.yaml` 中的 `conditions` 和 `tasks` 列表（或自动发现所有 `tasks/` 目录），然后展开矩阵。

### 5. Verifier 脚本支持 Python 和 PowerShell

为了兼容，新 task 的 verifier 写 `verifier.py`，旧 task 可临时用 `verifier.ps1`。`verifier.py` 通过 runner 传入的 JSON 环境变量读取 workspace/project/artifacts 路径，调用 `runner.unreal` 的 Python API 执行 UBT，并输出 `verifier_result.json`。

### 6. Adapter 抽象

```python
class Adapter(ABC):
    @abstractmethod
    def run(self, workspace_root: Path, instruction_path: Path,
            skills_root: Optional[Path], artifacts_dir: Path,
            timeout_minutes: int) -> AdapterResult: ...
```

- `OracleAdapter`：读取 `oracle.patch`，在 workspace 中应用 `git apply`。
- `ManualAdapter`：打印 workspace 路径，等待用户按 Enter 继续。
- 后续可扩展 `CodexAdapter`（调用 `codex exec`）。

---

## 实施顺序

### Phase 1: 核心框架（无 agent，验证环境）

1. 创建 `runner/config.py`：解析 `benchmark.yaml`，扫描 `tasks/`。
2. 创建 `runner/preflight.py`：检查 UE 环境、git、项目基线。
3. 创建 `runner/workspace.py`：安全复制项目、初始化 git、注入 skills、安全边界检查。
4. 创建 `runner/unreal.py`：解析 registry、调用 `Build.bat`（支持 clean 模式）。
5. 创建 `runner/metrics.py`：git diff 统计。
6. 创建 `runner/verifier.py`：执行 verifier 脚本，收集结果。
7. 创建 `runner/adapters/oracle.py`：应用 oracle.patch。
8. 创建 `runner/report.py`：汇总结果，生成 JSON + Markdown。
9. 创建 `tasks/tps-env-build-smoke`：验证 clean build 基线项目通过。

### Phase 2: 第一个正式任务

10. 设计 `tasks/tps-build-repair/setup.py`：注入多模块依赖缺失。
11. 设计 `tasks/tps-build-repair/verifier.py`：clean build + 静态检查。
12. 跑 `oracle` adapter，验证 oracle patch 100% 通过。
13. 跑 `manual` adapter，人工验证 verifier 流程正确。

### Phase 3: 集成 CLI

14. 实现 `runner/__main__.py`：
    - `python -m runner preflight`
    - `python -m runner run-matrix --adapter oracle`
    - `python -m runner report --run-id <id>`
15. 添加 `.bench/` 到 `.gitignore`。

---

## 验收标准

- [ ] `sample/TPSample` 只读，runner 不修改。
- [ ] `tps-env-build-smoke` oracle 通过，且 verifier 的 build duration > 30 秒（证明不是缓存）。
- [ ] `tps-build-repair` oracle 通过率为 100%。
- [ ] `tps-build-repair` 至少跑一次 `manual` adapter，verifier 能正确检测未修复的损坏（失败）。
- [ ] 报告包含 `overallPassed`、真实 `buildDurationSeconds`、git diff metrics。
- [ ] 安全边界检查通过：拒绝清理 `sample/TPSample`、仓库根目录、Engine 目录。

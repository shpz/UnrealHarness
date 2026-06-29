# UnrealHarness

[English](README_EN.md)

为编程智能体打造的虚幻引擎 Harness & Benchmark 套件。

让你的编程智能体狂奔在笔直的高速公路上，同时提供标准化的 Benchmark 来评估其能力。

兼容 Claude Code、OpenCode、Codex、Kimi Code 等支持 skill 的编程智能体。

## 仓库结构

| 目录 | 说明 |
|------|------|
| `skills/` | Harness Skills — 编程智能体可使用的技能 |
| `scripts/` | 安装与卸载脚本 |
| `benchmarks/` | Benchmark 套件 — 评估编程智能体能力的标准化任务 |
| `sample/` | 示例 UE5 项目（TPSample） |
| `docs/` | 设计与文档资料 |
| `tests/` | 测试相关 |

---

## 安装 Harness

推荐使用安装脚本

```
.\scripts\install.ps1
```

### 手动安装

将 `skills/` 目录下的 skill 文件夹复制到你的编程智能体 skills 目录：

| 编程智能体 | Skills 目录 |
|------|------------|
| Kimi Code | `~/.kimi/skills/` |
| OpenCode | `~/.opencode/skills/` |
| Codex | `~/.codex/skills/` |
| Claude Code | `~/.claude/skills/` |

安装后重启编程智能体即可自动识别。

### 卸载

推荐使用卸载脚本

```
.\scripts\uninstall.ps1
```

## Skills

### `ue-build` — 编译 UE5 项目

编译虚幻引擎 C++ 项目。

触发示例：
```
编译 UE5 项目
编译 D:\MyProject
debug 编译
```

- 自动查找与 `.uproject` 关联的引擎
- 默认 Development Editor，提到 debug/调试编译配置自动切换至 Debug Editor
- 支持 Windows，兼容 UE 5.x

---

## Benchmark

本仓库包含 `benchmarks/ue5-skillsbench/` — 一套用于评估编程智能体在 UE5 开发场景下能力的标准化 Benchmark。

### 运行 Benchmark

```bash
# 使用 Python 运行
python -m benchmarks.ue5-skillsbench.runner

# 或进入目录后运行
python -m runner
```

### 任务类型

- **环境检查** — 验证 UE5 环境是否正常
- **编译修复** — 在故意引入编译错误的项目中修复问题
- **多模块编译** — 验证跨模块编译能力

更多详情参见 `benchmarks/ue5-skillsbench/` 目录。

## 环境要求

- Python3
- 已安装虚幻引擎

## 许可证

MIT

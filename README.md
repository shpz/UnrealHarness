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
python scripts/install.py
```

常用选项：`--assistant claude|opencode|codex|kimi|all`（默认 all）、`--link`（开发时用符号链接代替复制）、`--force`（覆盖已存在的 skill）。

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
python scripts/uninstall.py
```

支持 `--assistant` 指定目标、`--force` 跳过确认。

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

### `ue-lsp` — 让 LSP 在 UE5 项目上真正可用

引导生成 `compile_commands.json`，让宿主智能体内置的 LSP（clangd）工具在 UE 项目上返回可信结果，并识别 clangd fallback 模式下的虚假诊断。

> **前置依赖：clangd（需在 PATH 中）**
>
> 本 skill 依赖 clangd，且必须能通过 PATH 找到——skill 的健康检查和宿主智能体的 LSP 客户端都从 PATH 解析 `clangd`。安装方式二选一：
>
> - **LLVM 官方安装包**（推荐）：从 [LLVM Releases](https://github.com/llvm/llvm-project/releases) 下载安装，安装时勾选 "Add LLVM to the system PATH"，无需额外配置。
> - **Visual Studio Installer**：单个组件中勾选"适用于 Windows 的 C++ Clang 工具"。注意 VS 安装的 clangd 位于 `<VS安装目录>\VC\Tools\Llvm\x64\bin`，**不会自动加入 PATH**，需手动将该目录添加到环境变量 PATH 中。
>
> 验证：新开终端运行 `clangd --version` 有输出即可。

触发示例：
```
用 LSP 检查这个文件有没有错误
GENERATED_BODY 报错了
CoreMinimal.h file not found
```

- `status.py` 一键诊断 LSP 健康度（ok / degraded / broken / invalid），并给出现成的 UBT `GenerateClangDatabase` 命令
- 识别 fallback 症状（`CoreMinimal.h` 找不到、`UCLASS` 未知类型、错误爆炸），防止智能体被假错误误导去"修复"正确代码
- 对外结论标注置信度（high / medium / low / invalid），UHT/generated header 相关诊断自动加 caveat
- 与 `ue-build` 分工：LSP 负责编译之间的快速局部查询，权威结论交给 UBT 编译

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
- **LSP 诊断** — 识别 clangd fallback 陷阱、基于 LSP 的混合代码审计（带真实编译认证的 ground truth）

更多详情参见 `benchmarks/ue5-skillsbench/` 目录。

## 环境要求

- Python3
- 已安装虚幻引擎

## 许可证

MIT

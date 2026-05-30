# UnrealHarness

为编程智能体打造的虚幻引擎 Harness 套件。

让你的编程智能体狂奔在笔直的高速公路上。

兼容 Claude Code、OpenCode、Codex、Kimi Code 等支持 skill 的编程智能体。

## 安装

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

## 环境要求

- Windows
- PowerShell
- 已安装虚幻引擎

## 许可证

MIT

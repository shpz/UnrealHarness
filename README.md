# UnrealHarness

为 AI 助手打造的 Unreal Engine 5 工具套件。兼容 Claude Code、OpenCode、Codex 等支持 skills 协议的 AI 助手。

## 功能

让 AI 助手能够直接编译和管理你的 UE5 C++ 项目，无需手动输入引擎路径或 UBT 参数。

- **自动引擎发现** — 从 `.uproject` 解析引擎关联，自动定位 Launcher 安装版或源码编译版引擎
- **一键编译** — 调用 UBT 编译项目，自动处理 Development / Debug 配置切换
- **错误重试** — 区分偶发性错误与编译错误，文件锁等问题自动重试

## 安装

将 `skills/` 目录下的 skill 文件夹复制到你的 AI 助手 skills 目录：

| 助手 | Skills 目录 |
|------|------------|
| Claude Code | `~/.claude/skills/` |
| OpenCode | `~/.opencode/skills/` |
| Codex | `~/.codex/skills/` |

安装后重启助手即可自动识别。

## Skills

### `ue-build` — 编译 UE5 项目

编译 Unreal Engine 5 C++ 项目。

触发示例：
```
编译 UE5 项目
编译 D:\MyProject
debug 编译
```

- 自动查找与 `.uproject` 关联的引擎
- 默认 Development Editor，提到 debug/调试自动切 Debug Editor
- 支持 Windows，兼容 UE 5.x

## 环境要求

- Windows
- PowerShell
- 已安装 Unreal Engine 5

## 许可证

MIT

# UnrealHarness

A harness suite for Unreal Engine, built for coding agents.

Let your coding agent sprint on a straight highway.

Compatible with skill-enabled coding agents including Claude Code, OpenCode, Codex, and Kimi Code.

## Installation

Recommended: use the installation script

```powershell
.\scripts\install.ps1
```

### Manual Installation

Copy the skill folders from the `skills/` directory to your coding agent's skills directory:

| Coding Agent | Skills Directory |
|------|------------|
| Kimi Code | `~/.kimi/skills/` |
| OpenCode | `~/.opencode/skills/` |
| Codex | `~/.codex/skills/` |
| Claude Code | `~/.claude/skills/` |

Restart your coding agent after installation for the skills to be recognized automatically.

### Uninstall

Recommended: use the uninstall script

```powershell
.\scripts\uninstall.ps1
```

## Skills

### `ue-build` — Build UE5 Projects

Build Unreal Engine C++ projects.

Trigger examples:
```
Build UE5 project
Build D:\MyProject
Debug build
```

- Automatically locates the engine associated with `.uproject`
- Defaults to Development Editor; switches to Debug Editor when debug/调试 is mentioned
- Supports Windows, compatible with UE 5.x

## Requirements

- Windows
- PowerShell
- Unreal Engine installed

## License

MIT

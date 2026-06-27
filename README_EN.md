# UnrealHarness

A harness & benchmark suite for Unreal Engine, built for coding agents.

Let your coding agent sprint on a straight highway, while providing standardized benchmarks to evaluate its capabilities.

Compatible with skill-enabled coding agents including Claude Code, OpenCode, Codex, and Kimi Code.

## Repository Structure

| Directory | Description |
|-----------|-------------|
| `skills/` | Harness Skills — skills usable by coding agents |
| `scripts/` | Installation and uninstallation scripts |
| `benchmarks/` | Benchmark suite — standardized tasks to evaluate coding agents |
| `sample/` | Sample UE5 project (TPSample) |
| `docs/` | Design documents and references |
| `tests/` | Test utilities |

---

## Install Harness

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

---

## Benchmark

This repository includes `benchmarks/ue5-skillsbench/` — a standardized benchmark suite for evaluating coding agents in UE5 development scenarios.

### Run Benchmark

```bash
# Run via Python module
python -m benchmarks.ue5-skillsbench.runner

# Or run from the directory
python -m runner
```

### Task Types

- **Environment Checks** — Verify UE5 environment setup
- **Build Repair** — Fix deliberately introduced compilation errors
- **Multi-Module Builds** — Validate cross-module compilation capability

For more details, see the `benchmarks/ue5-skillsbench/` directory.

## Requirements

- Windows
- PowerShell
- Unreal Engine installed (required for running benchmarks and harness)

## License

MIT

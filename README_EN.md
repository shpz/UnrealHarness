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
python -m benchmarks.ue5-skillsbench.runner preflight
python -m benchmarks.ue5-skillsbench.runner validate-task --task-id tps-build-engine-resolve --repeat 3
python -m benchmarks.ue5-skillsbench.runner run-single --task-id tps-build-engine-resolve --condition ue-build-only --adapter codex
python -m benchmarks.ue5-skillsbench.runner run-matrix --adapter codex --run-id <run-id>
python -m benchmarks.ue5-skillsbench.runner report --run-id <run-id>
```

`run-matrix` supports `--task-id`, `--task-filter`, `--condition`, and `--trials` to control task, condition, and trial selection.

### Task Types

- **Environment Checks** — Verify UE5 environment setup
- **Build Repair** — Fix deliberately introduced compilation errors
- **Multi-Module Builds** — Validate cross-module compilation capability

For more details, see `docs/ue5-skillsbench-framework-completion-design.md`. The old MVP plan is archived under `docs/archived/ue5-skillsbench-mvp/` and is no longer the implementation source of truth.

Operational docs:

- `docs/ue5-skillsbench-runbook.md`
- `docs/ue5-skillsbench-task-authoring-guide.md`

## Requirements

- Windows
- PowerShell
- Unreal Engine installed (required for running benchmarks and harness)

## License

MIT

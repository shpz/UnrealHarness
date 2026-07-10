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

```bash
python scripts/install.py
```

Common options: `--assistant claude|opencode|codex|kimi|all` (default: all), `--link` (symlink instead of copy, useful for development), `--force` (overwrite existing skills).

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

```bash
python scripts/uninstall.py
```

Supports `--assistant` to select a target and `--force` to skip confirmation.

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

### `ue-lsp` — Make LSP Actually Work on UE5 Projects

Bootstraps `compile_commands.json` generation so the host agent's built-in LSP (clangd) tools return trustworthy results on UE projects, and detects bogus diagnostics from clangd fallback mode.

> **Prerequisite: clangd (must be on PATH)**
>
> This skill depends on clangd, and it must be resolvable via PATH — both the skill's health check and the host agent's LSP client locate `clangd` through PATH. Install it one of two ways:
>
> - **Official LLVM installer** (recommended): download from [LLVM Releases](https://github.com/llvm/llvm-project/releases) and check "Add LLVM to the system PATH" during installation. No further setup needed.
> - **Visual Studio Installer**: select the individual component "C++ Clang tools for Windows". Note that VS installs clangd under `<VS install dir>\VC\Tools\Llvm\x64\bin` and does **not** add it to PATH automatically — you must add that directory to your PATH environment variable manually.
>
> Verify: open a new terminal and run `clangd --version`.

Trigger examples:
```
Check this file for errors with LSP
GENERATED_BODY is reporting errors
CoreMinimal.h file not found
```

- `status.py` diagnoses LSP health in one shot (ok / degraded / broken / invalid) and emits a ready-to-run UBT `GenerateClangDatabase` command
- Recognizes fallback symptoms (`CoreMinimal.h` not found, `UCLASS` unknown type, error explosion) to keep agents from "fixing" correct code based on fake errors
- Labels reported conclusions with confidence levels (high / medium / low / invalid); UHT/generated-header diagnostics automatically carry a caveat
- Division of labor with `ue-build`: LSP handles fast, local queries between builds; authoritative verdicts come from UBT compilation

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
- **LSP Diagnostics** — Detect clangd fallback traps and perform LSP-based mixed code audits (with build-certified ground truth)

For more details, see the `benchmarks/ue5-skillsbench/` directory.

## Requirements

- Windows
- Python 3
- Unreal Engine installed (required for running benchmarks and harness)

## License

MIT

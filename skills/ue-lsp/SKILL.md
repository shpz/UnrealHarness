---
name: ue-lsp
description: >
  当 agent 编写、审查或调试 Unreal Engine 5 C++，并且需要通过 clangd/LSP
  查询符号、类型、定义、引用、diagnostics、completion、signature help、workspace symbol、
  document symbols 或 code actions 时使用。触发词包括 UE5 LSP、clangd、compile_commands.json、
  GenerateClangDatabase、Unreal C++ API 查询、GENERATED_BODY diagnostics、.generated.h 问题，
  或任何需要确认 UE C++ 调用是否合法的场景。此 skill 只准备并查询 C++ language-server
  上下文；不解析 UHT，不分析 Blueprint 资产图，不自动应用重构，也不把 clangd diagnostics
  当作最终 UBT/UHT build 结论。
---

# UE5 LSP Skill

## 用途

使用 clangd 和宿主编辑器/agent 暴露的 LSP 工具，在当前 UE5 项目的真实编译上下文中回答 C++ 局部事实：符号在哪里定义、当前位置的类型或 overload 是什么、有哪些 references，以及当前文件是否有 C++ diagnostics。

核心链路是：

```text
.uproject + Engine + Target/Platform/Config
        -> UBT GenerateClangDatabase
        -> compile_commands.json
        -> clangd
        -> LSP query
        -> 带 confidence 和 caveats 的 agent-readable result
```

此 skill 不替代 `ue-build`。它用于判断 clangd 在修改前后能证明什么；当用户要求编译，或必须确认 UBT/UHT 真实结论时，仍然运行 `ue-build`。

## 第一步：检查状态

信任任何 UE C++ LSP 结果之前，先从 skill root 运行状态脚本：

```powershell
python "<skill-root>/status.py" --project "<Project.uproject>" --source-file "<File.cpp>"
```

把输出视为 `ue_lsp_status`：

```text
project_root
uproject_path
project_name
engine_root
target
platform
configuration
clangd_path
compile_commands_path
compile_commands_mtime
clangd_running
index_state: unknown
health: ok | degraded | broken
caveats
next_actions
generate_compile_commands_command
```

如果 `health` 是 `broken`，或者当前查询只能给出 `confidence: invalid`，不要把 LSP 结果描述成确定事实。先说明缺失前提，再只带 caveats 使用 fallback search。

## 编译数据库流程

clangd 需要 `compile_commands.json`。如果它缺失或可能过期，先准备 dry-run 命令，并向用户展示 project、target、platform、configuration、engine path 和预期输出位置；不要自动运行 UBT。

典型 Windows 命令形态：

```powershell
& "<EngineRoot>\Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.exe" -mode=GenerateClangDatabase -project="<Project.uproject>" -game -engine <Target> <Configuration> <Platform>
```

部分 UE 安装需要通过 `Engine\Build\BatchFiles\Build.bat` 调用，UE5 也常见 `dotnet "<EngineRoot>\Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.dll"` 形态。某些版本会把 `compile_commands.json` 写到 Engine root 而不是 project root。生成后必须重新检测实际输出路径；优先使用 `--compile-commands-dir=<dir>` 或在用户明确同意后写入最小 `.clangd`，不要静默复制或创建 symlink。

用户明确要求创建 `.clangd` 时，最小方向是：

```yaml
CompileFlags:
  CompilationDatabase: ./
Index:
  Background: Build
```

## 查询流程

clangd 可用时，使用宿主 agent 暴露的通用 LSP 工具。在 OpenCode 中，优先使用内置 LSP 工具查询 diagnostics、definition、references 和 symbols。对于 hover、completion、signature help 或 code actions，如果当前 harness 暴露对应 LSP/MCP 工具就使用；否则明确说明宿主没有暴露该 LSP 方法，并 fallback 到最接近的可用查询。

LSP position 使用 0-based 行列；从编辑器显示的 1-based 行列转换时要谨慎，并尊重客户端暴露的 position encoding。

每次查询都必须整理成 agent-readable 形式：

```text
query: hover | definition | references | workspace symbol | document symbols | completion | signature help | diagnostics | code actions
result: <agent-readable fact or empty result>
location: <file:line:column when available>
confidence: high | medium | low | invalid
caveats:
  - compile database stale or missing
  - generated header stale or missing
  - index incomplete
  - header compile command inferred
  - UHT/reflection semantics involved
next_actions:
  - read_definition
  - find_references
  - refresh_compile_database
  - refresh_generated_headers
  - search_source
  - check_docs
```

### `ue_lsp_diagnostics`

通过 clangd 打开当前文件后读取 diagnostics。include/macro 爆炸、standard library 缺失、`.generated.h` 缺失，以及 `GENERATED_BODY` 附近错误，应先分类为配置问题或 UHT/generated-header 风险；除非 UBT 也确认同样失败，不要直接当作业务代码错误。

### `ue_lsp_hover`

在具体 file position 查询类型、签名、宏信息或文档。只有当前文件使用真实 compile command 成功解析时，hover 才能作为较高可信度事实。

### `ue_lsp_definition`

确认当前位置绑定到哪个声明或实现。报告目标位于 project code、Engine code、plugin code 还是 generated code。

### `ue_lsp_references`

查询项目/Engine 中的使用点。clangd background index 仍在构建时，必须 caveat references 可能不完整。

### `ue_lsp_workspace_symbol`

不确定 UE API 路径时，先用 workspace symbol 搜索候选，不要猜 Engine 路径。如果 LSP miss 但静态搜索找到文本，标记 low confidence，并 caveat target/module/index 可能不可见。

### `ue_lsp_document_symbols`

编辑或审查大型 UE C++ 文件前，先用 document symbols 映射当前文件中的 class、function、field 和 method。

### `ue_lsp_completion`

查询当前位置可用成员、overload 候选，以及可能的 include/code-action 提示。UE macro completion 缺失不是符号不存在的证据。

### `ue_lsp_signature_help`

在函数调用位置确认当前参数序号和 overload 列表，尤其适合修改 UE API 调用前使用。

### `ue_lsp_code_actions`

只列出 code actions 或 quick fixes，尤其是 include fixes。除非用户明确要求且风险低，不要自动应用。

## 可信度规则

confidence: high

仅当 clangd 使用真实 compile command 解析当前文件、diagnostics 健康、且 LSP 返回精确符号结果时使用。

confidence: medium

当 LSP 返回结果，但 index 可能未完成、header compile command 是推断的、generated header 新鲜度不确定，或 diagnostics 有有限配置 caveats 时使用。

confidence: low

当 LSP 没有返回结果，只能依赖静态搜索；或 clangd 可能使用 fallback context；或 diagnostics 出现大面积 include/macro 失败时使用。

confidence: invalid

当没有 compile database、clangd 无法启动，或当前文件无法建立 AST 时使用。

## UHT 和 generated header 规则

不要自己解析 UHT。当问题涉及 `UCLASS`、`USTRUCT`、`UENUM`、`UINTERFACE`、`UPROPERTY`、`UFUNCTION`、`GENERATED_BODY`、`.generated.h`、Blueprint exposure、replication specifier 或 reflection metadata 时，必须添加 UHT caveat，并用 UBT/UHT 输出或官方文档确认。

缺失 `.generated.h` 或 `GENERATED_BODY` 附近 diagnostics 通常意味着 generated headers 缺失/过期，或者 compile database target 不对。不要只根据 clangd 诊断就重写业务代码；先通过真实 UBT/UHT 检查确认根因。

## fallback 策略

当 LSP 不可用或可信度低时：

1. 对 project 和 Engine source 做文本搜索，寻找候选符号。
2. 只有在展示命令并得到用户同意后，才刷新或生成 `compile_commands.json`。
3. reflection markers 相关问题通过显式 UBT/UHT 或 `ue-build` 刷新 generated headers。
4. 涉及 API 或工具链行为时，查官方 Unreal 或 clangd 文档。
5. 把结果报告为 hypothesis，不要包装成已由 C++ LSP 证明的事实。

## 示例流程

### 不确定 UE API 调用

运行 `ue_lsp_status`，用 `ue_lsp_workspace_symbol` 搜索候选 API，用 `ue_lsp_definition` 和 `ue_lsp_hover` 确认选中的 overload，在 callsite 用 `ue_lsp_signature_help` 检查参数，修改后读取 diagnostics。

### 审查 override 或函数调用

先用 document symbols 确认 clangd 能看见 class 和 method，再对可疑调用或 override 使用 hover 和 definition，用 references 查项目内相似用法，最后带 confidence 和 caveats 报告 diagnostics。

### generated header 问题

如果 diagnostics 涉及 `.generated.h`、`GENERATED_BODY` 或 UHT macros，即使 clangd 返回 C++ diagnostic，也要标记 medium/low confidence。只有用户同意时才请求或运行 UBT/UHT refresh；不要只根据 clangd 改 reflection specifiers。

### LSP miss 但源码命中

如果 workspace symbol 找不到，但静态搜索找到文本，说明该符号可能不在当前 target、module 或 clangd index 中。此时只能把直接文件读取或文档作为辅助证据。

---
name: ue-lsp
description: >
  当 agent 需要在 Unreal Engine 5 C++ 项目中使用 LSP（clangd）查询符号、定义、引用、
  diagnostics 时使用。此 skill 的核心职责是：确保 compile_commands.json 正确生成，
  让宿主 agent 的内置 LSP 工具在 UE 项目上真正可用；并识别 clangd fallback 模式下的
  虚假结果，防止 agent 被误导去"修复"正确的代码。触发词包括 UE5 LSP、clangd、
  compile_commands.json、GenerateClangDatabase、GENERATED_BODY 报错、.generated.h 问题、
  CoreMinimal.h file not found，或任何需要用 LSP 确认 UE C++ 代码的场景。
  此 skill 不解析 UHT，不分析 Blueprint 资产，不把 clangd diagnostics 当作最终 UBT 编译结论。
---

# UE5 LSP Skill

## 核心问题

宿主 agent（Claude Code、OpenCode 等）内置的 LSP 工具依赖 clangd，而 clangd 依赖
`compile_commands.json`。UE 项目默认没有这个文件。**没有它时 clangd 不会报错退出，
而是进入 fallback 模式，返回大量看似真实、实际错误的结果。**

实测 fallback 模式的表现（正确的 UE 代码上）：

- diagnostics 报出几十条 error：`'CoreMinimal.h' file not found`、`Unknown type name 'UCLASS'`、`GENERATED_BODY` 附近语法错误，直到 `too_many_errors` 截断。**这些全是环境问题，不是代码错误。**
- references 静默丢失跨文件结果（只返回当前文件内的命中，.cpp 中的引用全部丢失，且无任何"结果不完整"提示）。
- workspace symbol 查不到任何引擎符号（`ACharacter` 等 UE API 完全不可见）。
- document symbols 大纲能列出，但语义错误（`UPROPERTY` 被当作 Method）。

因此本 skill 的两条铁律：

1. **任何 LSP 查询前，先确认 compile_commands.json 存在且新鲜。** 不满足就先走"生成编译数据库"流程。
2. **看到 fallback 症状时，立即停止信任 LSP 结果。** 绝不根据 fallback diagnostics 修改代码。

## 第一步：状态检查

从 skill root 运行：

```powershell
python "<skill-root>/status.py" --project "<Project.uproject>" --source-file "<File.cpp>"
```

输出 JSON 包含 `health`（ok | degraded | broken | invalid）、`caveats`、`next_actions`
和现成的 `generate_compile_commands_command`。

- `health: ok` → 可以使用宿主内置 LSP 工具，按下文规则解读结果。
- `health: degraded` → 按 `caveats` 处理（如 compdb 在 engine root 而非项目根、clangd 不在 PATH）。
- `health: broken` → compile_commands.json 缺失。先走生成流程，不要先查询。
- `health: invalid` → 项目定位失败，按 `caveats` 修正参数。

## 第二步：生成 compile_commands.json

`status.py` 输出的 `generate_compile_commands_command` 已根据实际引擎安装选好了
UBT 调用形态。生成前向用户展示命令和预期输出位置，得到同意后执行。典型形态：

```powershell
& "<EngineRoot>\Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.exe" -mode=GenerateClangDatabase -project="<Project.uproject>" -game -engine <Target> <Configuration> <Platform>
```

注意事项：

- 部分 UE 版本把 `compile_commands.json` 写到 **Engine root 而不是 project root**。生成后重新运行 `status.py` 确认实际位置。
- 如果输出不在项目根，优先在项目根写一个最小 `.clangd` 指向它（需用户同意），不要复制或建 symlink：

```yaml
CompileFlags:
  CompilationDatabase: <compile_commands.json 所在目录>
Index:
  Background: Build
```

- 生成后 clangd 需要重启才会读取新数据库；宿主 LSP 客户端可能缓存旧会话，必要时提示用户重启 LSP 或 agent 会话。
- 首次查询后 background index 需要时间构建，references 结果在此期间可能不完整。

## 第三步：使用宿主内置 LSP

数据库就绪后，直接使用宿主 agent 暴露的 LSP 工具（diagnostics、definition、
references、symbols 等）。不要自己起 clangd 进程与宿主竞争。

高效用法：

- 不确定 UE API 时，先 workspace symbol 搜候选，再 definition/hover 确认，不要猜引擎路径。
- 编辑大文件前，先 document symbols 建立文件地图。
- 修改后立即对改动文件跑 diagnostics。
- LSP position 是 0-based 行列，从编辑器 1-based 转换时要小心。

## 结果解读规则

### fallback 症状识别（最高优先级）

查询结果出现以下任一特征时，判定 clangd 处于 fallback 或配置损坏状态：

- diagnostics 第一条是标准头文件或 `CoreMinimal.h` 找不到
- `UCLASS` / `UPROPERTY` / `UFUNCTION` / `GENERATED_BODY` 被报 `Unknown type name`
- 错误数量爆炸直至 `too_many_errors`

此时：停止信任本轮所有 LSP 结果，运行 `status.py` 诊断，走生成/修复流程。
**绝不根据这些 diagnostics 修改业务代码。**

### UHT 与 generated header

涉及 `UCLASS`、`USTRUCT`、`UPROPERTY`、`UFUNCTION`、`GENERATED_BODY`、`.generated.h`
的 diagnostics，即使 compdb 健康也要加 UHT caveat：generated header 可能过期或缺失。
根因确认交给 UBT/UHT（运行 `ue-build`），不要只根据 clangd 修改 reflection 相关代码。

### 可信度分级

对外报告 LSP 结论时标注 confidence：

- **high**：compdb 健康 + 当前文件用真实 compile command 解析成功 + 精确符号命中。
- **medium**：有结果但 index 可能未建完、header 的 compile command 是推断的、或 generated header 新鲜度不确定。
- **low**：LSP 无结果只能靠文本搜索，或出现局部 include 失败。
- **invalid**：无 compdb / clangd 未启动 / fallback 症状。此级别的结果不得作为修改代码的依据。

references 在 background index 构建期间必须 caveat "可能不完整"；
workspace symbol 查不到但文本搜索能找到时，标记 low 并说明符号可能不在当前 target/module/index 中。

## 与 ue-build 的分工

clangd 说"没问题"不等于 UBT 能编过；clangd 说"有问题"也不等于代码真的错了。
需要权威结论（提交前验证、修复 UHT 问题、用户要求编译）时，运行 `ue-build`。
本 skill 负责的是编译之间的快速、局部、带置信度的事实查询。

## fallback 策略

LSP 不可用或 confidence 为 low/invalid 时：

1. 对 project 和 Engine source 做文本搜索，结果报告为 hypothesis 而非 LSP 证明的事实。
2. 生成/刷新 compile_commands.json（展示命令并获同意后）。
3. reflection 相关问题用 `ue-build` 刷新 generated headers。
4. API 或工具链行为查官方 Unreal / clangd 文档。

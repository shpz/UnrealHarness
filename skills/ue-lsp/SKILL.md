---
name: ue-lsp
description: >
  在 Unreal Engine 5 C++ 项目中检查 clangd 前置条件，并执行 definition、hover、
  references、implementation 和安全的 rename preview。适用于 UE5 LSP、clangd、
  compile_commands.json、GenerateClangDatabase、GENERATED_BODY、.generated.h、
  CoreMinimal.h not found、符号跳转、引用影响和语义重命名场景。本 skill 不解析
  Blueprint 资产，不把 clangd diagnostics 当作最终 UBT/UHT 编译结论。
---

# UE5 LSP Skill

## 使用原则

1. 每次语义查询前先运行 `status.py` 或 `query.py status`。
2. `compile_commands.json` 必须位于当前项目根；Engine root 中的遗留文件只作为 external/legacy state 报告，绝不读取、覆盖或删除。
3. 宿主原生 LSP 明确可用且调用结果可观测时，优先使用宿主工具。
4. 宿主没有 definition/references/implementation/hover/rename 能力，或无法观察实际调用时，使用本 skill 的 `query.py` managed clangd。
5. managed clangd 只属于当前 ProjectRoot，不终止或修改 IDE、宿主 agent、其他项目的 clangd。
6. fallback diagnostics 不能作为修改 UE 业务源码的依据；权威构建结论仍由 UBT/UHT 提供。

## 状态检查与 workspace-local compdb

```powershell
python "<skill-root>/status.py" `
  --project "D:\work\TPSample\TPSample.uproject" `
  --source-file "Source\TPSample\Foo.cpp"
```

也可以使用统一入口：

```powershell
python "<skill-root>/query.py" status --project "D:\work\TPSample\TPSample.uproject"
```

关注字段：

- `expected_compile_commands_path`：固定为 `<ProjectRoot>\compile_commands.json`。
- `compile_commands_location`：正常流程固定为 `project_root`。
- `compile_commands_health`：`missing`、`malformed`、`empty`、`wrong-workspace`、`source-not-covered`、`stale` 或 `valid`。
- `legacy_engine_compile_commands_path`：只报告，不使用、不修改。
- `health`、`caveats`、`next_actions`：决定查询是否可信。

`status.py` 输出的生成命令包含：

```text
-mode=GenerateClangDatabase
-project="<Project.uproject>"
-OutputDir="<ProjectRoot>"
```

预期产物只能是 `<ProjectRoot>\compile_commands.json`。如果旧 UE 不支持 `-OutputDir`，应明确报告兼容问题并停止；不得静默回退到 Engine root。

compdb 刷新依据是 `.uproject`、`*.Build.cs`、`*.Target.cs`、translation unit 新增/删除，或请求的 `.cpp` 未覆盖。普通 `.cpp` 内容比 compdb 新不代表数据库过期。

## Managed clangd 查询

查询会自动启动项目服务；不必预先执行 `start`。服务状态位于：

```text
<ProjectRoot>\.ue-lsp\
  server.json
  server.log
  clangd.log
  cache\
  lock
```

显式管理命令：

```powershell
python "<skill-root>/query.py" start --project "TPSample.uproject"
python "<skill-root>/query.py" stop  --project "TPSample.uproject"
```

`stop` 只通知当前项目 `server.json` 中带认证 token 的 managed server。compdb 或 clangd 发生变化时，下一次查询自动重启该项目服务。

### Definition

```powershell
python "<skill-root>/query.py" definition `
  --project "TPSample.uproject" `
  --file "Source/TPSample/Foo.cpp" `
  --line 12 --column 8
```

### Hover

```powershell
python "<skill-root>/query.py" hover `
  --project "TPSample.uproject" `
  --file "Source/TPSample/Foo.h" `
  --line 20 --column 10
```

### References

```powershell
python "<skill-root>/query.py" references `
  --project "TPSample.uproject" `
  --file "Source/TPSample/Foo.h" `
  --line 20 --column 10 `
  --exclude-declaration `
  --wait-for-index --index-timeout 180
```

### Implementation

```powershell
python "<skill-root>/query.py" implementation `
  --project "TPSample.uproject" `
  --file "Source/TPSample/BenchSemanticAction.h" `
  --line 19 --column 16 `
  --wait-for-index
```

### Rename preview

```powershell
python "<skill-root>/query.py" rename-preview `
  --project "TPSample.uproject" `
  --file "Source/TPSample/Foo.h" `
  --line 20 --column 10 `
  --new-name NewName `
  --wait-for-index
```

CLI 的 line/column 是 1-based，JSON 输出也是 1-based。`rename-preview` 不写文件：`files`/`workspace_edit` 只列出项目 `Source` 中的可操作预览；clangd 提议的 `Intermediate`、Engine 或 external edits 会列入 `excluded_files` 并标明 scope，避免误改生成文件。

## 索引完整性和置信度

- `index_state: ready` 才能把跨文件 references/implementation/rename 视为完成。
- 索引未完成时，`possibly_incomplete=true`，confidence 最高为 `medium`。
- 需要精确影响面时使用 `--wait-for-index`，并设置适合 UE 首次索引的 `--index-timeout`。
- `high`：workspace compdb 有效、精确符号命中、需要的 background index 已 ready。
- `medium`：有结果但索引未完成、header compile command 是推断的，或 generated header 新鲜度未由 UHT 确认。
- `low`：只能依靠文本搜索或局部 include 失败。
- `invalid`：compdb 缺失/损坏、clangd 不可用或 fallback 症状明显。

## fallback 与 UHT caveat

出现 `CoreMinimal.h not found`、`UCLASS`/`UPROPERTY`/`UFUNCTION`/`GENERATED_BODY` unknown、或 errors 爆炸到 `too_many_errors` 时，停止信任本轮 LSP 结果，重新检查 compdb。不要据此修改业务代码。

`.generated.h` 通常位于 `Intermediate/Build/.../Inc/...`，不要求存在于源文件旁。涉及 reflection 的结论始终附加 UHT caveat，并用 `ue-build`/UBT/UHT 验证。

## Telemetry

如果 runner 给子进程设置 `UE_LSP_TRACE_PATH`，每次 query 会 best-effort 追加一条 JSONL。记录 operation、位置、结果数、index state、完整性、confidence、耗时和错误码，不记录源码内容。trace 写入失败不得影响查询。

trace 是 skill 使用的可观测证据，但不是 agent 全部推理来源的绝对证明；报告中的 usage confidence 仍应标记为 partial 或 evidence-based-partial。

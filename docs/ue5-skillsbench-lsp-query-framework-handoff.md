# UE5 SkillsBench LSP Query Framework Handoff

日期：2026-07-16

## 完成范围

本次实现把 ue-lsp 从“compdb 使用说明”升级为可执行、可观测的语义查询框架：

- `status.py` 只接受项目根的 workspace-local compdb，并验证 JSON、entry、workspace、translation unit、项目元数据和 response file。
- `query.py` 提供持久 managed clangd，会话按 ProjectRoot 隔离。
- Codex/Kimi adapter 注入 trial-local telemetry 环境变量。
- runner 汇总 JSONL trace 到 `result.json`，report 汇总 LSP 使用和对照指标。
- 旧 LSP trap setup 不再删除 Engine root compdb 或其他项目配置。

## 架构

`query.py` CLI 不为每个查询冷启动 clangd。第一次语义查询会启动：

```text
query.py CLI
  -> 127.0.0.1 random port + token
  -> project-local Python managed server
  -> one clangd stdio process
  -> JSON-RPC initialize/didOpen/query/shutdown
```

项目状态目录：

```text
<ProjectRoot>\.ue-lsp\
  server.json   # pid/port/token/project/clangd/version/compdb signature
  server.log
  clangd.log
  cache\        # XDG cache hint for clangd
  lock          # atomic startup lock, present only while starting
```

`server.json` 的 token 防止其他本地进程误操作服务。compdb path/mtime/size 或 clangd path 改变时，CLI 只重启该项目记录的 managed server。Windows 强制清理前还会核对进程命令行包含当前 `query.py _serve` 和 ProjectRoot；不会终止 IDE 或其他项目 clangd。

runner 在 agent 结束后 best-effort 调用当前项目的 `query.py stop`，避免矩阵 trial 累积后台进程。样例项目 `.gitignore` 已忽略 `.ue-lsp`；clangd 19.1.5 自己仍把 background-index shards 写到 ProjectRoot 的 `.cache/clangd/index`，该目录原本已忽略。当前 clangd 的 `--help-hidden` 没有可用的 index-storage 路径 flag，因此没有添加虚构参数。

## Workspace-local compdb

生成命令固定包含：

```text
-OutputDir="<ProjectRoot>"
```

正常路径固定为：

```text
<ProjectRoot>\compile_commands.json
```

状态 JSON 的主要字段：

```json
{
  "expected_compile_commands_path": "...\\Project\\compile_commands.json",
  "compile_commands_path": "...\\Project\\compile_commands.json",
  "compile_commands_location": "project_root",
  "compile_commands_health": "valid"
}
```

`compile_commands_health` 支持 `missing`、`malformed`、`empty`、`wrong-workspace`、`source-not-covered`、`stale`、`valid`。校验兼容 UTF-8 BOM，并检查：

- 根节点是非空数组；
- entry 有 `file` 和 `command`/`arguments`；
- 至少覆盖项目 `Source` 中一个 `.cpp`；
- 请求的 `.cpp` 有精确 entry；
- 不包含明显来自其他 `D:\br\...\workspace\TPSample` 的 TU；
- `.uproject`、Build.cs、Target.cs 和 TU 集合未改变；
- `command` 引用的 `.rsp` 仍存在。

普通 `.cpp` 内容 mtime 不触发 stale。Engine root 的遗留 compdb 只写入 `legacy_engine_compile_commands_path` caveat，不读取、不覆盖、不删除。

`.generated.h` 不再按源文件同目录检查。包含 reflection/UHT 代码时只给出“用 UBT/UHT 验证”的 caveat。

## Query CLI

```powershell
python skills/ue-lsp/query.py status --project D:\work\TPSample\TPSample.uproject
python skills/ue-lsp/query.py start  --project D:\work\TPSample\TPSample.uproject
python skills/ue-lsp/query.py stop   --project D:\work\TPSample\TPSample.uproject

python skills/ue-lsp/query.py definition `
  --project D:\work\TPSample\TPSample.uproject `
  --file Source/TPSample/Foo.cpp --line 12 --column 8

python skills/ue-lsp/query.py hover `
  --project D:\work\TPSample\TPSample.uproject `
  --file Source/TPSample/Foo.h --line 20 --column 10

python skills/ue-lsp/query.py references `
  --project D:\work\TPSample\TPSample.uproject `
  --file Source/TPSample/Foo.h --line 20 --column 10 `
  --exclude-declaration --wait-for-index --index-timeout 180

python skills/ue-lsp/query.py implementation `
  --project D:\work\TPSample\TPSample.uproject `
  --file Source/TPSample/Interface.h --line 19 --column 16 `
  --wait-for-index

python skills/ue-lsp/query.py rename-preview `
  --project D:\work\TPSample\TPSample.uproject `
  --file Source/TPSample/Foo.h --line 20 --column 10 `
  --new-name NewName --wait-for-index
```

CLI 和输出位置均为 1-based；内部 LSP 使用 0-based。实现处理 Windows file URI、Location、Location[]、LocationLink[]、MarkupContent、MarkedString、WorkspaceEdit `changes`/`documentChanges`、server request/notification、`$/progress` 和 `clangd/indexingProgress`。

background index 未 ready 时，跨文件操作返回 `possibly_incomplete=true` 且 confidence 不高于 medium。`rename-preview` 永不写文件；项目 Source edits 位于 `files`，Intermediate/Engine/external 建议位于 `excluded_files` 并标记 scope。

## Telemetry

CodexAdapter 和 KimiCodeAdapter 只给 agent 子进程注入：

```text
UE_LSP_TRACE_PATH=<artifacts>\lsp-query-trace.jsonl
UE_LSP_PROJECT_PATH=<workspace project path>
```

单条 JSONL：

```json
{
  "timestamp": "2026-07-16T10:41:50.088973+00:00",
  "query_id": "...",
  "operation": "rename-preview",
  "project_root": "D:\\br\\...\\TPSample",
  "file": "Source/TPSample/BenchSemanticRename/BenchAbilityRouter.h",
  "line": 14,
  "column": 10,
  "result_count": 4,
  "index_state": "ready",
  "possibly_incomplete": false,
  "confidence": "high",
  "elapsed_ms": 2.847,
  "status": "success",
  "error_code": null
}
```

写入使用短生命周期 lock file，失败时静默降级，不记录源码。runner `result.json.lsp` 包含 query count、semantic query count、operation counts、failed/incomplete counts、mean query ms 和 malformed line count。无 trace 时返回零值，不影响 trial。

report 新增平均 semantic query count、使用 LSP 的 trial 数、failed/incomplete counts、usage evidence confidence、no-skills 对 ue-lsp-only 的 pass-rate delta 和 agent duration delta。trace 只视为 evidence-based-partial 证据，不视为绝对证明。

## 测试结果

单元测试：

- `python -m unittest discover -s skills/ue-lsp/tests -v`：22 passed。
- `python -m unittest discover -s benchmarks/ue5-skillsbench/tests -v`：4 passed。
- `python -m py_compile ...`：通过。
- `git diff --check`：通过。

UE5.7/clangd 19.1.5 独立 workspace：

- `D:\br\lsp-query-integration-reference-20260716`：status valid；references 精确返回 3 个目标；definition 跳到手写 `.cpp`；hover 正常。
- `D:\br\lsp-query-integration-implementation-20260716`：implementation 返回 Direct 和 Shared 两个实际 provider，可用于完成继承映射。
- `D:\br\lsp-query-integration-rename-20260716`：rename preview 仅暴露 4 个目标 Source 文件；UHT generated edit 被放入 `excluded_files`；无 honeypot；未改文件。
- compdb mtime 改变后 server PID 从 16392 变为 43300，验证自动重启。
- mixed-audit setup 隔离测试确认只删除 trial-local compdb/.clangd，Engine compdb SHA-256 不变。

Oracle + clean build：

- `framework-final-lsp-semantic-rename-oracle-20260716`：passed。
- `framework-final-lsp-implementation-map-oracle-20260716`：passed。
- `framework-final-lsp-reference-impact-oracle-20260716`：passed。

## Kimi smoke

```powershell
cd D:\ArtWorkspace\UnrealHarness\benchmarks\ue5-skillsbench

$tasks = @(
  "tps-lsp-semantic-rename",
  "tps-lsp-implementation-map",
  "tps-lsp-reference-impact"
)

foreach ($task in $tasks) {
  python -m runner run-single `
    --task-id $task `
    --condition ue-lsp-only `
    --adapter kimi-code `
    --trial 1 `
    --run-id "kimi-lsp-query-smoke-$task-20260716" `
    --timeout-minutes 45 `
    --verifier-timeout 45
}
```

检查每个 `D:\br\<run-id>\result.json` 的 `lsp` 字段，以及 artifacts 下的 `lsp-query-trace.jsonl`。

## 已知限制与后续工作

- clangd 19.1.5 没有可用的 background-index storage path flag；Windows 上 shards 仍由 clangd 放到项目 `.cache/clangd/index`，但该路径已按 workspace 隔离并被 git 忽略。
- index ready 依赖 clangd progress notification；首次完整 UE 索引可能需要 1–3 分钟，应使用 `--wait-for-index`。
- implementation 返回语义 override/provider 位置，不会直接枚举“未 override、完全继承 provider”的 concrete class；任务仍需结合 definition/hover/类继承关系。
- 本次没有实现 rename `--apply`，只有 preview。
- 尚未运行完整 Kimi 3×2×3 矩阵；下一步先跑上述 smoke，再跑 no-skills/ue-lsp-only 对照并生成 report。

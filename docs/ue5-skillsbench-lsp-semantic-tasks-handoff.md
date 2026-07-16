# UE5 SkillsBench 语义 LSP 任务交接

## 当前状态

已增加三个面向 clangd/LSP 语义能力的正式任务：

1. `tps-lsp-semantic-rename`
2. `tps-lsp-implementation-map`
3. `tps-lsp-reference-impact`

三个任务均已在本机 UE5.7 环境使用 `oracle` adapter 完成端到端验证，包含：

- fixture 注入；
- workspace-local `compile_commands.json` 生成和内容校验；
- oracle patch 应用；
- verifier 语义结果检查；
- UnrealHeaderTool；
- `TPSampleEditor Win64 Development` clean build。

验证结果：三个任务全部通过。

| 任务 | Oracle run ID | Verifier | Clean build |
| --- | --- | --- | --- |
| `tps-lsp-semantic-rename` | `dev-semantic-rename-oracle-2` | 通过 | 通过，约 34 秒 |
| `tps-lsp-implementation-map` | `dev-implementation-map-oracle-2` | 通过 | 通过，约 33 秒 |
| `tps-lsp-reference-impact` | `dev-reference-impact-oracle` | 通过 | 通过，约 33 秒 |

Oracle 产物位于 `D:\br\<run-id>\`。

## 任务说明

### 1. `tps-lsp-semantic-rename`

目标：将指定的 `UBenchAbilityRouter::TriggerAbility` 安全重命名为 `ActivateAbility`。

fixture 中同时存在：

- 目标声明和定义；
- 两个跨文件真实调用点；
- 其他类型的同名成员函数；
- 同名自由函数；
- 注释和字符串；
- `ReferenceHoneypots/` 下 generated-looking 同名文本。

verifier 要求：

- 四个目标源码文件被正确修改；
- 同名诱饵和 generated-looking 快照保持不变；
- 不允许修改其他 `Source/` 或 `Config/` 文件；
- `semantic_rename_report.json` 正确；
- 报告中的 compdb 是有效、非空并包含 TPSample translation unit 的 JSON；
- clean build 通过。

主要失败分类：

- `missing-report`
- `invalid-compdb`
- `incomplete-rename`
- `decoy-modified`
- `generated-modified`
- `out-of-scope-change`
- `build`

### 2. `tps-lsp-implementation-map`

目标：分析 `IBenchSemanticAction`，列出所有真正满足接口的可实例化类，并指出实际提供 override 的类。

fixture 覆盖：

- 直接实现接口；
- 父类实现接口；
- 子类继承父类实现；
- 子类再次 override；
- 拥有同名同签名函数但没有实现接口的诱饵类。

正确集合包含：

- `ABenchSharedActionActor`
- `ABenchDirectActionActor`
- `ABenchInheritedActionActor`
- `ABenchOverrideActionActor`

其中 `ABenchInheritedActionActor` 的 provider 是 `ABenchSharedActionActor`。

verifier 要求：

- `implementation_map.json` 的类集合必须完全一致，不能漏报或多报；
- provider、class header、implementation file 必须正确；
- `Source/` 和 `Config/` 保持不变；
- compdb 有效；
- clean build 通过。

主要失败分类：

- `missing-report`
- `invalid-compdb`
- `wrong-interface`
- `wrong-class-set`
- `wrong-mapping`
- `source-modified`
- `build`

### 3. `tps-lsp-reference-impact`

目标：找出对以下精确重载的调用和取地址引用：

```cpp
UBenchReferenceRouter::RouteEvent(const FName&)
```

fixture 中同时存在：

- 目标签名的声明和定义；
- 两个普通调用；
- 一个成员函数取地址；
- `RouteEvent(int32)` 重载及调用；
- 其他类的同名同签名函数及调用；
- 注释、字符串和 generated-looking 文本。

verifier 接受的精确引用集合为：

| 文件 | 行 | 类型 |
| --- | ---: | --- |
| `BenchReferenceCallSitesA.cpp` | 7 | `call` |
| `BenchReferenceCallSitesB.cpp` | 7 | `call` |
| `BenchReferenceMemberPointer.cpp` | 7 | `address_of` |

verifier 要求引用集合完全一致，不接受声明、定义、错误重载或同名诱饵。

主要失败分类：

- `missing-report`
- `invalid-compdb`
- `wrong-target`
- `wrong-references`
- `source-modified`
- `honeypot-modified`
- `build`

## Compdb 隔离策略

三个任务共用 `tasks/_lsp_task_support.py`。

setup 使用 UE5.7 UBT：

```text
-mode=GenerateClangDatabase
-OutputDir=<trial workspace project root>
```

每个 trial 的 `compile_commands.json` 都位于自己的 `D:\br\<run-id>\workspace\TPSample\`，不会读写共享的 Engine root compdb。

setup 会拒绝以下 compdb：

- 文件不存在；
- JSON 无法解析；
- 根节点不是非空数组；
- 不包含 `Source/TPSample` 下的 `.cpp` translation unit。

## Kimi 建议测试流程

工作目录：

```powershell
cd D:\ArtWorkspace\UnrealHarness\benchmarks\ue5-skillsbench
```

先运行环境检查：

```powershell
python -m runner preflight
```

### 第一阶段：每个任务各跑一次 smoke

```powershell
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
        --run-id "kimi-lsp-smoke-$task" `
        --timeout-minutes 35 `
        --verifier-timeout 30
}
```

如果 smoke 正常，再跑对照矩阵。

### 第二阶段：`no-skills` 对比 `ue-lsp-only`

建议先跑每条件 3 次；稳定后再增加到 5 次。

```powershell
$prefix = "kimi-lsp-semantic-001"
$tasks = @(
    "tps-lsp-semantic-rename",
    "tps-lsp-implementation-map",
    "tps-lsp-reference-impact"
)
$conditions = @("no-skills", "ue-lsp-only")

foreach ($task in $tasks) {
    foreach ($condition in $conditions) {
        foreach ($trial in 1..3) {
            $runId = "$prefix-$task-$condition-t$trial"
            python -m runner run-single `
                --task-id $task `
                --condition $condition `
                --adapter kimi-code `
                --trial $trial `
                --run-id $runId `
                --timeout-minutes 35 `
                --verifier-timeout 30
        }
    }
}
```

生成汇总报告：

```powershell
python -m runner report --run-id "kimi-lsp-semantic-001"
```

报告输出到：

- `benchmarks/ue5-skillsbench/reports/kimi-lsp-semantic-001-summary.md`
- `benchmarks/ue5-skillsbench/reports/kimi-lsp-semantic-001-results.json`

`runner/report.py` 已按 `tps-lsp-*` 任务使用 `ue-lsp-only` 与 `no-skills` 计算 pass-rate delta 和 normalized gain。

## 单次失败排查

每个 run 的关键文件位于：

```text
D:\br\<run-id>\artifacts\
```

优先查看：

1. `setup.stderr.log`：fixture 或 compdb 生成问题；
2. `agent.stdout.log`：Kimi 的分析和实际操作；
3. `git.diff`：最终改动；
4. `verifier_result.json`：精确失败分类；
5. `build.log` 和 `ubt.log`：UHT/UBT 构建问题。

如果 `agent.stdout.log` 显示 Kimi 没有原生 definition/references/rename 工具，只是读取了 skill 后使用文本搜索，需要在结果结论中记录这一点。

## 结果解读注意事项

1. verifier 验证的是最终语义结果，不验证 agent 必须调用 LSP。skill usage confidence 仍然是 partial。
2. `no-skills` 条件也可能通过；关键指标包括 pass rate、错误类型和 agent duration，而不只是单次 pass/fail。
3. `tps-lsp-semantic-rename` 最容易观察同名诱饵造成的错误改动。
4. `tps-lsp-implementation-map` 最容易观察继承 provider 是否被识别。
5. `tps-lsp-reference-impact` 最容易观察 overload、声明/定义和同名函数是否被错误计入。
6. 当前 Kimi adapter 没有独立的 LSP usage telemetry。需要从 `agent.stdout.log` 人工判断其查询路径。

## 相关文件

- `benchmarks/ue5-skillsbench/tasks/_lsp_task_support.py`
- `benchmarks/ue5-skillsbench/tasks/tps-lsp-semantic-rename/`
- `benchmarks/ue5-skillsbench/tasks/tps-lsp-implementation-map/`
- `benchmarks/ue5-skillsbench/tasks/tps-lsp-reference-impact/`
- `benchmarks/ue5-skillsbench/runner/report.py`

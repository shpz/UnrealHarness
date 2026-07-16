将 `Source/TPSample/BenchSemanticRename/` 中的成员函数
`UBenchAbilityRouter::TriggerAbility(const FName&)` 安全重命名为 `ActivateAbility`。

要求：

- 更新该符号在手写源码中的声明、定义和真实调用点，使项目可以编译。
- 不要修改其他类或自由函数中恰好同名的 `TriggerAbility`。
- 不要修改字符串、注释、`ReferenceHoneypots/` 或 `Intermediate/` 中的同名文本。
- 不要修改 `Config/` 或引擎源码。

项目根目录已经提供可用的 `compile_commands.json`。将查询证据写入项目根目录的
`semantic_rename_report.json`：

```json
{
    "compile_commands_path": "compile_commands.json",
    "old_symbol": "UBenchAbilityRouter::TriggerAbility",
    "new_symbol": "UBenchAbilityRouter::ActivateAbility"
}
```

`compile_commands_path` 可以是绝对路径，也可以是相对项目根目录的路径。

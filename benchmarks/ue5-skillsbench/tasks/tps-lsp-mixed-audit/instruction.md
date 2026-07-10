审计 `Source/TPSample/Bench/` 目录下的 5 个 C++ 类，判断每个类是否存在 C++ 代码错误（即需要修改代码才能通过编译的错误）：

- `BenchScoreTracker`
- `BenchSignalRelay`
- `BenchAimSolver`
- `BenchPatrolRoute`
- `BenchWaveDirector`

将审计结果写入项目根目录的 `lsp_audit.json`。格式说明（`SomeClass` 仅为格式示意，具体每个类的 true/false 由你的审计结论决定）：

```json
{
    "compile_commands_path": "<你使用的 compile_commands.json 的绝对路径>",
    "files": {
        "SomeClassWithoutErrors": { "has_code_errors": false },
        "SomeClassWithErrors": { "has_code_errors": true, "error_symbol": "<出错的符号名>", "error_line": 42 }
    }
}
```

要求：

- `files` 必须覆盖上述 5 个类，每个类都给出 `has_code_errors` 判定。
- 判定为 `true` 的类，必须同时给出 `error_symbol`（出错处涉及的符号名）和 `error_line`（.cpp 文件中的出错行号）。
- `compile_commands_path` 必须是真实存在的文件路径。
- 不要修改 `Source/` 或 `Config/` 目录下的任何文件。

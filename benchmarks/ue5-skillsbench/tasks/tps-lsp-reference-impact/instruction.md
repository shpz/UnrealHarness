分析符号：

```cpp
UBenchReferenceRouter::RouteEvent(const FName& EventName)
```

在 `Source/TPSample/BenchReferenceImpact/` 中找出所有对这个**精确重载**的使用位置。

计入：

- 普通成员函数调用；
- 对该成员函数的取地址。

不计入：

- 目标函数的声明和定义；
- `RouteEvent(int32)` 重载；
- 其他类的同名函数及其调用；
- 注释、字符串、`ReferenceHoneypots/` 或 `Intermediate/` 中的文本。

将结果写入项目根目录的 `reference_impact.json`：

```json
{
    "compile_commands_path": "compile_commands.json",
    "target": "UBenchReferenceRouter::RouteEvent(const FName&)",
    "references": [
        {
            "file": "Source/TPSample/BenchReferenceImpact/Example.cpp",
            "line": 12,
            "kind": "call"
        }
    ]
}
```

行号使用编辑器中的 1-based 行号。不要修改 `Source/`、`Config/`、`ReferenceHoneypots/` 或引擎源码。
项目根目录已经提供可用的 `compile_commands.json`。

使用 LSP（clangd）检查 `Source/TPSample/TPSampleCharacter.h` 是否存在真实的 C++ 代码错误。

当前 trial 的项目根没有 `compile_commands.json`；Engine 安装目录或其他项目中的遗留数据库属于外部状态，不能作为本 trial 的编译数据库。

将结论写入项目根目录的 `lsp_verdict.json`，格式如下：

```json
{
    "has_code_errors": false,
    "reason": "简要说明你的判断依据"
}
```

`has_code_errors` 为 `true` 表示该文件存在需要修改代码才能解决的 C++ 错误；为 `false` 表示该文件代码本身没有问题。

不要修改 `Source/` 或 `Config/` 目录下的任何文件。

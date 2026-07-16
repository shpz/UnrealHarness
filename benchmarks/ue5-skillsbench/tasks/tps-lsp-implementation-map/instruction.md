分析 `Source/TPSample/BenchImplementationMap/` 中的 `IBenchSemanticAction` 接口。

找出该目录下所有满足以下条件的类：

1. 类不是接口本身；
2. 类不是仅仅拥有同名函数，而是真正实现或继承了 `IBenchSemanticAction`；
3. 类是可实例化的具体类；
4. 如果实现由父类继承，指出真正声明 `ExecuteAction(const FName&)` override 的 provider 类。

将结果写入项目根目录的 `implementation_map.json`：

```json
{
    "compile_commands_path": "compile_commands.json",
    "interface": "IBenchSemanticAction",
    "concrete_classes": {
        "SomeConcreteClass": {
            "provider_class": "ClassThatDeclaresTheOverride",
            "class_header": "Source/TPSample/BenchImplementationMap/SomeConcreteClass.h",
            "implementation_file": "Source/TPSample/BenchImplementationMap/Provider.cpp"
        }
    }
}
```

`concrete_classes` 只能包含真正满足接口的具体类。不要修改 `Source/`、`Config/` 或引擎源码。
项目根目录已经提供可用的 `compile_commands.json`。

# UE5 自动化测试模式速查卡

## 1. 测试模块结构

被测模块 `<RuntimeModule>` 旁建 `<RuntimeModule>Test` 测试模块，一个 .cpp 覆盖一个功能域。

### Build.cs 模板

```csharp
using UnrealBuildTool;

public class RuntimeModuleTest : ModuleRules
{
    public RuntimeModuleTest(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] {
            "Core",
            "UnrealEd",           // Editor 测试模块需要
            "<RuntimeModule>"     // 被测模块
        });
        PrivateDependencyModuleNames.AddRange(new[] {
            "CoreUObject",
            "Engine"
        });
    }
}
```

**警告：`UnrealEd` 只能进 Editor 测试模块，不要放进 Game target。** 被测模块的 Public 头文件必须可达；`CoreUObject` / `Engine` 提供 UObject 与 World 支持。

---

## 2. 测试宏选择

默认用 `IMPLEMENT_SIMPLE_AUTOMATION_TEST`。项目未建立 AutomationSpec 体系时不要混用 `Describe` / `It` / 参数化测试。

| Flag 组合 | 场景 |
|-----------|------|
| `ApplicationContextMask \| EngineFilter` | 纯 C++、UObject、数组、错误处理、委托、性能/内存测试；默认首选，可配合 `-nullrhi` 无头运行 |
| `EditorContext \| ProductFilter` | 需要 Editor 模块、PIE、World、Actor、Component 生命周期时才用 |

原则：纯逻辑和数据测试优先 non-PIE headless；只有 World / Actor / Component 生命周期或真实 Editor 行为必须参与时才用 PIE + latent command。
原始写法：`ApplicationContextMask | EngineFilter`，`EditorContext | ProductFilter`。

---

## 3. 命名约定

`<Project>.<Domain>.<Feature>.<Scenario>`

| 层级 | 示例 |
|------|------|
| Domain | Inventory、SaveGame、ErrorHandling、Performance、AI、UI、Component |
| Feature | Stack、Serialization、Memory、Speed |
| Scenario | AddItem、RoundTrip、BufferPressure、DelegateChain |

- 用 `.` 分层，不用下划线
- 回归测试的 Scenario 描述行为：`SaveFailureDedupe` > `ErrorDedupeBug`
- 性能测试固定前缀：`Performance.Speed.*` / `Performance.Memory.*`

---

## 4. 断言模式

```cpp
TestEqual(TEXT("Msg"), Actual, Expected);   // 数值、枚举、字符串精确匹配
TestTrue(TEXT("Msg"), Condition);           // 布尔条件成立
TestFalse(TEXT("Msg"), Condition);
TestNotNull(TEXT("Msg"), Pointer);          // UObject 创建成功
```

浮点与批量数据不适合精确相等，用容差比较（tolerance comparison，逐元素 `FMath::Abs(A[i]-B[i]) > Tolerance` 即失败），不匹配时 `AddError(TEXT("Values differ beyond tolerance"))` 输出定位信息；诊断信息用 `AddInfo`（只写日志，不标失败）。

---

## 5. 辅助工具类模式

每个测试文件可配一个 `FGenericTestUtils` 或 `F*TestUtils` 静态工具类；跨文件复用时放测试模块 Public 头文件。典型职责：

- **数据生成**：`GenerateLinearValues(Count, Start, Step)`、`ValidateRange(Values, Min, Max)`
- **文件 I/O**：用 `FPaths::ProjectDir()` 拼 fixture 路径，`FFileHelper::LoadFileToArray` 加载，失败时 `UE_LOG` 报错

### 错误追踪辅助（UErrorTestHelper 模式）

```cpp
UCLASS()
class RUNTIMEMODULETEST_API UErrorTestHelper : public UObject
{
    GENERATED_BODY()
public:
    UPROPERTY() int32 BroadcastCount = 0;
    UPROPERTY() FString LastErrorMessage;
    UFUNCTION()
    void OnErrorReceived(const FGenericErrorInfo& ErrorInfo)
    { BroadcastCount++; LastErrorMessage = ErrorInfo.Message; }
    void Reset() { BroadcastCount = 0; LastErrorMessage.Empty(); }
};
// 用法：AddDynamic 绑定 → 触发错误 → TestEqual(BroadcastCount, 1)
```

---

## 6. Testable 子类模式（白盒测试）

用 `UTestable*` 子类 + `using` 声明暴露 protected 成员，零侵入生产代码：

```cpp
UCLASS()
class RUNTIMEMODULETEST_API UTestableGenericWriter : public UGenericWriter
{
    GENERATED_BODY()
public:
    using UGenericWriter::InternalWriteChunk;   // 暴露 protected 方法
    using UGenericWriter::OutputDirectory;      // 暴露 protected 成员
    bool GetIsWriting() const { return bIsWriting; }
};
```

---

## 7. PIE 集成测试（Latent Commands）

需要运行时 World 时用 `ADD_LATENT_AUTOMATION_COMMAND`：

```cpp
IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FComponent_Lifecycle_SpawnAndTick,
    "MyProject.Component.Lifecycle.SpawnAndTick",
    EAutomationTestFlags::EditorContext |
    EAutomationTestFlags::ProductFilter
)

bool FComponent_Lifecycle_SpawnAndTick::RunTest(const FString& Parameters)
{
    TSharedPtr<bool> bComponentTicked = MakeShared<bool>(false);

    ADD_LATENT_AUTOMATION_COMMAND(FStartPIECommand(true));
    ADD_LATENT_AUTOMATION_COMMAND(FFunctionLatentCommand([this, bComponentTicked]()
    {
        UWorld* World = GEditor->GetEditorWorldContext().World();
        TestNotNull(TEXT("World exists"), World);
        UGenericComponent* Component = NewObject<UGenericComponent>(World->GetCurrentLevel());
        Component->Activate(true);
        *bComponentTicked = Component->HasTickedForTest();
        return true;
    }));
    ADD_LATENT_AUTOMATION_COMMAND(FWaitLatentCommand(1.0f));
    ADD_LATENT_AUTOMATION_COMMAND(FFunctionLatentCommand([this, bComponentTicked]()
    {
        TestTrue(TEXT("Component ticked"), *bComponentTicked);
        return true;
    }));
    ADD_LATENT_AUTOMATION_COMMAND(FEndPlayMapCommand());

    return true;
}
```

**关键模式：**
- Lambda 是异步执行的，跨 Lambda 共享可变状态必须用 `TSharedPtr`，不能捕获局部变量引用
- `FStartPIECommand(true)` 以独立进程启动 PIE（更干净）
- `FWaitLatentCommand(seconds)` 等待时间流逝
- 最后必须 `FEndPlayMapCommand()` 清理，否则 World 状态污染后续测试

---

## 8. 性能测试模式

速度：`FPerformanceTimer` 包装 `FPlatformTime::Seconds()`，断言耗时红线并 `AddInfo` 输出实测值：

```cpp
FPerformanceTimer Timer;   // Start() 记录 FPlatformTime::Seconds()
Timer.Start();
const int32 Count = UGenericFunctionLibrary::ProcessValues(Source);
const double Elapsed = Timer.ElapsedMs();
TestEqual(TEXT("All values processed"), Count, Source.Num());
TestTrue(TEXT("Batch processing under 100ms"), Elapsed < 100.0);  // 红线断言
AddInfo(FString::Printf(TEXT("Elapsed: %.2f ms"), Elapsed));
```

内存：`FMemorySnapshot` 包装 `FPlatformMemory::GetStats()`，前后快照差值断言增长红线；比较前必须 `CollectGarbage`：

```cpp
FMemorySnapshot Before; Before.Capture();       // FPlatformMemory::GetStats()
for (int32 i = 0; i < 100; ++i) { /* 反复执行被测操作 */ }
CollectGarbage(GARBAGE_COLLECTION_KEEPFLAGS);   // 排除未回收对象干扰
FMemorySnapshot After; After.Capture();
const SIZE_T Delta = After.UsedPhysicalDelta(Before);
TestTrue(TEXT("Memory growth under 10MB"), Delta < 10 * 1024 * 1024);  // 红线断言
AddInfo(FString::Printf(TEXT("Delta: %.2f MB"), Delta / (1024.0 * 1024.0)));
```

两类测试都用 `ApplicationContextMask | EngineFilter`，命名归入 `Performance.Speed.*` / `Performance.Memory.*`。

---

## 9. 回归测试标记

测试名用**行为描述**，Bug ID 保留在注释中：

```cpp
// 名称：MyProject.ErrorHandling.SaveFailureDedupe
bool FErrorHandling_SaveFailureDedupe::RunTest(const FString& Parameters)
{
    // Regression: HIGH #2 — failed saves used to broadcast duplicate errors.
    UTestableGenericWriter* Writer = NewObject<UTestableGenericWriter>();
    UErrorTestHelper* Helper = NewObject<UErrorTestHelper>();
    Writer->OnError.AddDynamic(Helper, &UErrorTestHelper::OnErrorReceived);
    for (int32 i = 0; i < 10; ++i) { Writer->WriteToInvalidPath(); }
    TestEqual(TEXT("Error deduplicated to single broadcast"), Helper->BroadcastCount, 1);
    return true;
}
```

---

## 10. 测试文件组织

```
<RuntimeModule>Test/
├── <Feature>Test.cpp / .h        # 一个 .cpp 一个功能域；.h 放共享 TestUtils 与 Testable 子类
├── PerformanceTest.cpp           # 速度 + 内存合一文件，按命名前缀区分
├── ErrorHandlingTest.cpp         # 错误处理与回归测试
└── Helpers/                      # ErrorTestHelper.h、Testable<Class>.h
```

---

## 11. 常见陷阱

| 陷阱 | 表现 | 解决 |
|------|------|------|
| **浮点精确比较** | `TestEqual(0.1f + 0.2f, 0.3f)` 失败 | 用容差比较：`FMath::Abs(A-B) < Tolerance` |
| **Lambda 捕获引用** | PIE Latent Command 中捕获局部变量悬空 | 用 `TSharedPtr` 共享状态 |
| **未清理 PIE** | 后续测试失败，World 状态污染 | 最后总是 `FEndPlayMapCommand()` |
| **GC 时机问题** | UObject 在测试中“消失” | `NewObject` 后手动 `AddToRoot()` 或确保有 Outer |
| **文件路径硬编码** | 测试在 CI 上找不到资源 | 用 `FPaths::ProjectDir()` 拼接绝对路径 |
| **委托绑定生命周期** | 测试结束后委托仍触发 | 测试末尾 `RemoveAll` 或让 Helper UObject 自动解绑 |
| **时序敏感测试** | 本地通过 CI 失败 | 用 `FWaitLatentCommand` 而非 `FPlatformProcess::Sleep` |

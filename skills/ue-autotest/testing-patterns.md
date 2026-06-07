# UE5 自动化测试模式指南

> 从已验证的 UE5 Editor 与 non-PIE 自动化测试实践中提炼出的通用 C++ 测试编写模式。

---

## 1. 测试模块结构

### 最小可运行模块

```
Source/
├── <RuntimeModule>/              # 被测模块
└── <RuntimeModule>Test/          # 测试模块
    ├── <RuntimeModule>Test.Build.cs
    └── <Feature>Test.cpp         # 一个文件一个功能域
```

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

**关键依赖：**
- `UnrealEd` — Editor 测试模块依赖；不要放进 Game target
- 被测模块 — 确保 Public 头文件可达
- `CoreUObject` / `Engine` — 基础 UObject 和 World 支持

---

## 2. 测试宏选择

默认使用 `IMPLEMENT_SIMPLE_AUTOMATION_TEST`。除非项目已经建立 `AutomationSpec` 体系，否则不要混用 `Describe`、`It` 或参数化测试。

```cpp
IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FInventory_Stack_AddItem,
    "MyProject.Inventory.Stack.AddItem",
    EAutomationTestFlags::ApplicationContextMask |
    EAutomationTestFlags::EngineFilter
)

bool FInventory_Stack_AddItem::RunTest(const FString& Parameters)
{
    FInventoryStack Stack;

    const bool bAdded = Stack.AddItem(TEXT("Potion"), 2);

    TestTrue(TEXT("Item add succeeds"), bAdded);
    TestEqual(TEXT("Quantity is stored"), Stack.GetQuantity(TEXT("Potion")), 2);

    return true;
}
```

### 何时用哪种 Flag

| Flag 组合 | 场景 | 运行方式 |
|-----------|------|----------|
| `ApplicationContextMask \| EngineFilter` | 纯 C++、UObject、数组、错误处理、委托、性能/内存测试 | 默认首选，可配合 `-nullrhi` 无头运行 |
| `EditorContext \| ProductFilter` | 需要 Editor 模块、PIE、World、Actor、Component 生命周期 | 仅在确实需要编辑器/PIE 时使用 |

纯逻辑和数据测试优先用 non-PIE headless；只有 World、Actor、Component 生命周期或真实 Editor 行为必须参与时才使用 PIE/latent command。

---

## 3. 命名约定

### 测试全名格式

```
<Project>.<Domain>.<Feature>.<Scenario>
```

**通用实例：**

| 测试全名 | 含义 |
|---------|------|
| `MyProject.Inventory.Stack.AddItem` | 背包域 / 堆叠功能 / 添加物品 |
| `MyProject.SaveGame.Serialization.RoundTrip` | 存档域 / 序列化功能 / 往返校验 |
| `MyProject.ErrorHandling.SaveFailureDedupe` | 错误处理 / 保存失败 / 错误去重回归测试 |
| `MyProject.Performance.Memory.BufferPressure` | 性能 / 内存 / 缓冲压力测试 |

### 命名层级语义

```
MyProject.<Domain>.<Feature>.<Scenario>

Domain:   Inventory | SaveGame | ErrorHandling | Performance | AI | UI | Component
Feature:  Stack | Serialization | Memory | Speed | RegisterConsumer
Scenario: AddItem | RoundTrip | BufferPressure | DelegateChain
```

**规则：**
- 不要用下划线分隔，用 `.` 层级
- 回归测试在 Scenario 中体现行为：`SaveFailureDedupe` > `ErrorDedupeBug`
- 性能测试固定前缀：`MyProject.Performance.Speed.*` 或 `MyProject.Performance.Memory.*`

---

## 4. 断言模式

### 4.1 标准宏（UE 内置）

```cpp
TestEqual(TEXT("Message"), Actual, Expected);
TestTrue(TEXT("Message"), Condition);
TestFalse(TEXT("Message"), Condition);
TestNotNull(TEXT("Message"), Pointer);
```

**使用场景：**
- `TestEqual` — 数值、枚举、字符串精确匹配
- `TestTrue/TestFalse` — 布尔状态、条件成立
- `TestNotNull` — UObject 创建成功验证

### 4.2 自定义验证

浮点、批量数据或复杂结构不适合精确相等时，使用自定义比较并通过 `AddError` 输出定位信息。

```cpp
static bool ArraysEqualWithTolerance(
    const TArray<float>& A,
    const TArray<float>& B,
    float Tolerance = 1.0f)
{
    if (A.Num() != B.Num()) return false;
    for (int32 Index = 0; Index < A.Num(); ++Index)
    {
        if (FMath::Abs(A[Index] - B[Index]) > Tolerance) return false;
    }
    return true;
}

if (!FGenericTestUtils::ArraysEqualWithTolerance(Expected, Actual, 0.01f))
{
    AddError(TEXT("Values differ beyond tolerance"));
}
```

**原则：**
- 精确匹配用 `TestEqual`
- 浮点和批量数据用自定义比较 + `AddError`
- 诊断信息用 `AddInfo`（输出到日志，不标记失败）

---

## 5. 辅助工具类模式

每个测试文件可以有对应的 `F*TestUtils` 静态工具类；跨文件复用时放到测试模块 Public 头文件。

### 5.1 数据生成工具

```cpp
class FGenericTestUtils
{
public:
    static TArray<float> GenerateLinearValues(int32 Count, float Start = 0.0f, float Step = 1.0f)
    {
        TArray<float> Values;
        Values.Reserve(Count);

        for (int32 Index = 0; Index < Count; ++Index)
        {
            Values.Add(Start + Step * Index);
        }
        return Values;
    }

    static bool ValidateRange(const TArray<float>& Values, float Min = -1.0f, float Max = 1.0f)
    {
        for (float Value : Values)
        {
            if (Value < Min || Value > Max) return false;
        }
        return true;
    }
};
```

### 5.2 文件 I/O 工具

```cpp
class FFileTestUtils
{
public:
    static TArray<uint8> LoadFixtureBytes(const FString& Filename)
    {
        const FString ProjectDir = FPaths::ProjectDir();
        const FString FullPath = FPaths::Combine(ProjectDir, TEXT("TestFixtures"), Filename);

        TArray<uint8> Bytes;
        if (!FFileHelper::LoadFileToArray(Bytes, *FullPath))
        {
            UE_LOG(LogTemp, Error, TEXT("Failed to load %s"), *FullPath);
        }
        return Bytes;
    }

    static bool ParseHeader(const TArray<uint8>& Bytes, FExampleHeader& OutHeader);
};
```

### 5.3 错误追踪辅助（可复用的 UObject 模式）

`UErrorTestHelper` 是一个通用模式：用专门的 UObject 绑定和追踪委托广播。

```cpp
UCLASS()
class RUNTIMEMODULETEST_API UErrorTestHelper : public UObject
{
    GENERATED_BODY()

public:
    UPROPERTY()
    int32 BroadcastCount = 0;

    UPROPERTY()
    FString LastErrorMessage;

    UFUNCTION()
    void OnErrorReceived(const FGenericErrorInfo& ErrorInfo)
    {
        BroadcastCount++;
        LastErrorMessage = ErrorInfo.Message;
    }

    void Reset() { BroadcastCount = 0; LastErrorMessage.Empty(); }
};

UErrorTestHelper* Helper = NewObject<UErrorTestHelper>();
Handler->OnError.AddDynamic(Helper, &UErrorTestHelper::OnErrorReceived);

Handler->ProcessInvalidData();

TestEqual(TEXT("Error broadcast exactly once"), Helper->BroadcastCount, 1);
```

---

## 6. Testable 子类模式（白盒测试）

用 **Testable 子类**暴露 protected 成员，避免为了测试修改生产代码的访问控制。

```cpp
UCLASS()
class RUNTIMEMODULE_API UGenericWriter : public UObject
{
    GENERATED_BODY()
protected:
    FString OutputDirectory;
    bool bIsWriting = false;
    void InternalWriteChunk(const TArray<uint8>& Data);
};

UCLASS()
class RUNTIMEMODULETEST_API UTestableGenericWriter : public UGenericWriter
{
    GENERATED_BODY()
public:
    using UGenericWriter::InternalWriteChunk;
    using UGenericWriter::OutputDirectory;

    bool GetIsWriting() const { return bIsWriting; }
};

UTestableGenericWriter* Writer = NewObject<UTestableGenericWriter>();
Writer->OutputDirectory = TEXT("/Invalid/Path");
Writer->InternalWriteChunk(TestData);
```

**优势：**
- 零侵入生产代码
- 可测试内部状态而不破坏封装
- 易于清理（测试模块隔离）

---

## 7. PIE 集成测试（Latent Commands）

需要运行时 World 的测试使用 UE 的 Latent Automation Command 模式。

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
- `TSharedPtr` 跨 Lambda 共享可变状态（不能用捕获引用，Lambda 是异步执行的）
- `FStartPIECommand(true)` — 以独立进程启动 PIE（更干净）
- `FWaitLatentCommand(seconds)` — 等待时间流逝
- 最后必须 `FEndPlayMapCommand()` 清理

---

## 8. 性能测试模式

### 8.1 速度测试

```cpp
struct FPerformanceTimer
{
    double StartTime;
    void Start() { StartTime = FPlatformTime::Seconds(); }
    double ElapsedMs() const { return (FPlatformTime::Seconds() - StartTime) * 1000.0; }
};

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FPerformance_Speed_BatchProcessing,
    "MyProject.Performance.Speed.BatchProcessing",
    EAutomationTestFlags::EditorContext |
    EAutomationTestFlags::ProductFilter
)

bool FPerformance_Speed_BatchProcessing::RunTest(const FString& Parameters)
{
    TArray<float> Source = FGenericTestUtils::GenerateLinearValues(100000);

    FPerformanceTimer Timer;
    Timer.Start();
    const int32 ProcessedCount = UGenericFunctionLibrary::ProcessValues(Source);
    const double Elapsed = Timer.ElapsedMs();

    TestEqual(TEXT("All values processed"), ProcessedCount, Source.Num());
    TestTrue(TEXT("Batch processing under 100ms"), Elapsed < 100.0);
    AddInfo(FString::Printf(TEXT("Elapsed: %.2f ms"), Elapsed));

    return true;
}
```

### 8.2 内存测试

```cpp
struct FMemorySnapshot
{
    FPlatformMemoryStats Stats;
    void Capture() { Stats = FPlatformMemory::GetStats(); }
    SIZE_T UsedPhysicalDelta(const FMemorySnapshot& Other) const
    {
        return Stats.UsedPhysical - Other.Stats.UsedPhysical;
    }
};

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FPerformance_Memory_LargeDataStability,
    "MyProject.Performance.Memory.LargeDataStability",
    EAutomationTestFlags::EditorContext |
    EAutomationTestFlags::ProductFilter
)

bool FPerformance_Memory_LargeDataStability::RunTest(const FString& Parameters)
{
    FMemorySnapshot Before;
    Before.Capture();

    for (int32 Index = 0; Index < 100; ++Index)
    {
        auto* Processor = NewObject<UGenericDataProcessor>();
        Processor->ProcessLargeDataSet();
    }

    CollectGarbage(GARBAGE_COLLECTION_KEEPFLAGS);

    FMemorySnapshot After;
    After.Capture();
    const SIZE_T Delta = After.UsedPhysicalDelta(Before);
    const SIZE_T MaxAllowed = 10 * 1024 * 1024;

    TestTrue(TEXT("Memory growth under 10MB after 100 iterations"), Delta < MaxAllowed);
    AddInfo(FString::Printf(TEXT("Memory delta: %.2f MB"), Delta / (1024.0 * 1024.0)));

    return true;
}
```

---

## 9. 回归测试标记

用**行为描述**而非 Bug ID 来命名回归测试，注释中可以保留 Bug ID。

```cpp
IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FErrorHandling_SaveFailureDedupe,
    "MyProject.ErrorHandling.SaveFailureDedupe",
    EAutomationTestFlags::EditorContext |
    EAutomationTestFlags::ProductFilter
)

bool FErrorHandling_SaveFailureDedupe::RunTest(const FString& Parameters)
{
    // Regression: HIGH #2 — failed saves used to broadcast duplicate errors.

    UTestableGenericWriter* Writer = NewObject<UTestableGenericWriter>();
    UErrorTestHelper* Helper = NewObject<UErrorTestHelper>();
    Writer->OnError.AddDynamic(Helper, &UErrorTestHelper::OnErrorReceived);

    for (int32 Index = 0; Index < 10; ++Index)
    {
        Writer->WriteToInvalidPath();
    }

    TestEqual(TEXT("Error deduplicated to single broadcast"), Helper->BroadcastCount, 1);

    return true;
}
```

---

## 10. 测试文件组织建议

```
<RuntimeModule>Test/
├── <Feature>Test.cpp             # 功能测试（一个文件一个域）
├── <Feature>Test.h               # 共享的 TestUtils 和 Testable 子类
├── PerformanceTest.cpp           # 性能测试（速度和内存放一起）
├── ErrorHandlingTest.cpp         # 错误处理和回归测试
└── Helpers/
    ├── ErrorTestHelper.h         # 可复用的 UErrorTestHelper
    └── Testable<Class>.h         # 各种 Testable 子类
```

**原则：**
- 一个 `.cpp` 文件覆盖一个**功能域**
- 工具类放 `.h` 文件，供同模块多个 `.cpp` 共享
- 性能测试（速度 + 内存）可以合在一个文件，按命名前缀区分
- 回归测试放在 ErrorHandling 文件或对应功能域文件

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

---
name: ue-autotest
description: >
  Use when a user needs Unreal Engine 5 Automation Framework tests written, run headlessly,
  debugged, auto-fixed, or reported for a UE C++ project.
  仅适用于 Unreal Engine 上下文：当前项目包含 `.uproject` 文件，或用户明确提到
  UE/Unreal/虚幻引擎。非 UE 项目的测试请求不要使用本 skill。
  触发词包括：
  "运行UE5测试"、"run tests"、"自动化测试"、"unit test"、"integration test"、
  "regression test"、"系统测试"、"测试项目"、"跑一下测试"、"编译并测试"、
  "测试模块"、"测试功能模块"、"怎么写测试"、"添加测试"、"测试模式"、
  "IMPLEMENT_SIMPLE_AUTOMATION_TEST"、"UE5测试范例"，或任何涉及 UE5 Automation Framework
  测试执行或测试编写的工作流。测试脚本内部会通过 ue-build 的 build.py 自动完成编译；
  仅当用户只要求编译而不运行测试时，才单独使用 `ue-build` skill。默认运行所有测试模块，除非用户指定特定模块。
---

# UE5 自动化测试 Skill

## 用途

1. **编写测试** — 根据项目现有测试模块和 [`testing-patterns.md`](./testing-patterns.md) 生成可编译的 UE5 C++ Automation Test 代码。
2. **执行测试** — 运行 `scripts/autotest.py`：脚本自动调用 `ue-build/build.py` 编译 Editor target，再使用 `UnrealEditor-Cmd.exe` 无头运行 Automation tests，生成 JSON 和 Markdown 报告。
3. **闭环修复** — 根据编译错误、Automation 失败、日志和报告定位测试代码问题，最小修改后重新运行同一 scope，直到通过或用户要求停止。

## 场景契约

每次写入或修改测试代码前，先定义至少 3 个场景并把它们落实为测试名：

| 场景 | 必填内容 |
|------|----------|
| Happy path | 正常输入/正常对象生命周期的二进制通过条件 |
| Edge | 空数据、边界值、无效配置、重复调用或委托广播次数 |
| Regression | 邻近功能不被破坏的具体行为 |

每个场景必须写明：Automation test full name、运行 scope、通过条件、真实运行命令。没有这些内容，不要先写生产或测试代码。

## 测试编写指南

当用户询问"怎么写 UE5 测试"、"给 XX 功能加测试"、"测试模式"时：

1. **必须先完整读取** 本 skill 目录下的 [`testing-patterns.md`](./testing-patterns.md)。在读取该文件之前，不要编写任何测试代码；生成的代码必须遵循其中的模块结构、宏选择、命名、断言和工具类模式。
2. **扫描** 用户指定的源文件，理解被测 API 的接口和边界
3. **选择落点**：优先放到现有 `Source/*Test/Private/<Feature>Test.cpp`；共享工具放到同模块 `Public/*.h`。只有项目没有测试模块时，才创建 `<ModuleName>Test` Editor 模块。
4. **检查模块注册**：测试模块必须出现在 `.uproject` 的 `Modules` 中，类型为 `Editor`；Editor target 的 `ExtraModuleNames` 必须包含测试模块；Game target 不要包含 `UnrealEd` 依赖测试模块。
5. **生成并写入** 测试代码，包括：
   - 默认使用 `IMPLEMENT_SIMPLE_AUTOMATION_TEST` 和 `bool FName::RunTest(const FString& Parameters)`
   - 纯数据/对象测试使用 `EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::EngineFilter`
   - 需要 PIE、World、Actor、Component 生命周期时使用 `EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter` 和 latent commands
   - 命名遵循 `<Project>.<Domain>.<Feature>.<Scenario>`，例如 `MyProject.ErrorHandling.SaveFailureDedupe`
   - 断言使用 `TestEqual`、`TestTrue`、`TestFalse`、`TestNotNull`；浮点/批量数据用容差比较加 `AddError`
   - 辅助工具类使用 `F*TestUtils`、`UTestable*`、`UErrorTestHelper`，不要为了测试改生产代码访问级别
6. **运行 `scripts/autotest.py` 编译并执行新增测试 scope**（脚本内部通过 `ue-build/build.py` 编译），失败后只修复测试代码或用户明确要求的生产 bug。

> 详细模式和代码范例参见 [`testing-patterns.md`](./testing-patterns.md)。

### 最小测试模板

```cpp
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMyFeatureHappyPathTest,
    "MyProject.Domain.Feature.HappyPath",
    EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FMyFeatureHappyPathTest::RunTest(const FString& Parameters)
{
    TestTrue(TEXT("Expected binary condition is true"), true);
    return true;
}
```

## 执行流程

### 步骤 1：解析用户意图

确定测试范围：
- `"all"` / `"所有测试"` / 未指定 → 运行全部测试模块
- 模块名（如 `"CoreGameplayTest"`）→ 运行该模块的测试
- 通配符（如 `"MyProject.AI.*"`）→ 匹配对应前缀的测试
- `"unit"` / `"integration"` / `"performance"` → 根据 `config.yaml` 的 `moduleCategories` 过滤。该映射默认为空，需先在 `config.yaml` 中按项目实际模块名填写，否则分类 scope 会报错

### 步骤 2：确认项目路径

检查当前工作目录中是否有 `.uproject` 文件：
- 单个 → 自动使用
- 多个 → 提示用户指定
- 无 → 询问项目路径

### 步骤 3：调用测试脚本

执行 Python 脚本（脚本内部会自动调用 `ue-build/build.py` 完成编译，不要在此之外手写 UBT 命令或重复编译）：

```bash
python "<skill-root>/scripts/autotest.py" --project "<项目目录或.uproject>" --scope "<范围>"
```

多个 scope 可以一次运行：

```bash
python "<skill-root>/scripts/autotest.py" --project "<项目目录>" --scope "MyProject.Input.*" --scope "MyProject.Error.*"
```

或用 `+` 连接：

```bash
python "<skill-root>/scripts/autotest.py" --project "<项目目录>" --scope "MyProject.Input.*+MyProject.Error.*"
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--project`, `-p` | 项目目录或 `.uproject` 文件 | 自动检测当前目录 |
| `--scope`, `-s` | 测试范围：`all`、模块名、通配前缀或分类关键字 | `all` |
| `--config`, `-c` | 编译配置：Development, Debug | Development |
| `--no-null-rhi` | 不附加 `-nullrhi`（PIE/渲染类测试用） | 关 |
| `--skip-build` | 跳过编译步骤（代码未变更时） | 关 |

脚本会自动：
- 扫描 `Source/*Test/` 目录发现测试模块
- 调用 `../ue-build/build.py` 编译项目
- 单次启动 `UnrealEditor-Cmd.exe` 无头运行所有匹配模块的测试（多个过滤器用 `+` 连接，避免多次编辑器启动和重复执行）
- 默认追加 `-nullrhi`、`-TestExit="Automation Test Queue Empty"` 和 `-ReportExportPath="Saved\Automation\Reports\Raw\<Scope>"`
- 优先解析 `Saved/Automation/Reports/Raw/<Scope>/index.json` 获取结果；缺少原生报告时回退解析 `Saved/Logs/UnrealEditor-Cmd.log`
- 按各模块的自动化前缀把测试结果归属到对应模块
- 生成 `Saved/Automation/autotest_results.json`
- 调用 `report.py` 生成 Markdown 报告

纯数据、转换、错误处理、委托、内存/性能测试保留默认 `-nullrhi`。PIE、媒体、渲染、运行时设备或需要真实 viewport 的测试加 `--no-null-rhi` 重新运行。

### 步骤 4：检查结果并交互

读取 `autotest_results.json`：

| 场景 | 处理 |
|------|------|
| 全部通过 | 向用户展示成功摘要，报告已落盘到 `Saved/Automation/Reports/` |
| 有失败 | 生成失败摘要（失败测试名 + 错误信息），询问用户是否修复 |

### 步骤 5：修复交互循环

有失败时必须闭环：
1. 读取 `autotest_results.json`、Markdown 报告、模块 `logFile` 和 `rawReportDir`
2. 判断失败类型：编译错误、测试断言失败、Automation 未发现测试、超时、编辑器启动失败
3. 定位到新增/修改的测试文件；除非日志证明生产代码 bug，否则只修测试代码
4. 用最小修改修复后，重新运行 `autotest.py` 并传入同一 `--scope`（脚本会自动重新编译）
5. 循环直到通过、用户要求停止，或失败被确认为外部环境问题

**修复红线（任何情况下禁止）：**
- 禁止删除失败的测试或断言
- 禁止弱化断言让测试通过：不得把 `TestEqual` 换成恒真条件、不得注释掉断言、不得把容差放宽到失去校验意义
- 禁止修改测试的预期值去迁就错误的实际行为，除非能引用日志/代码证明原预期本身写错
- 如果确认断言本身有误，修改前必须向用户说明理由并获得确认

用户选择"落盘"时：
- 生成完整报告（含失败详情）
- 保存到 `Saved/Automation/Reports/`

### 步骤 6：反馈结果

- **全部通过**：展示汇总统计和报告路径
- **有失败且已修复**：展示修复后的结果
- **有失败且落盘**：展示报告路径和失败摘要

## 错误处理

| 错误 | 处理 |
|------|------|
| 未找到测试模块 | 报告"未检测到测试模块，请检查 Source/ 目录" |
| 编译失败 | 报告编译错误，不进入测试阶段 |
| 编辑器进程超时 | 强制终止，报告超时 |
| 日志解析失败 | 回退到原始日志输出 |
| 测试数为 0 | 检查 scope 是否是完整 Automation 前缀；检查测试模块是否在 `.uproject` 和 Editor target 注册 |
| `--project` 是目录 | 允许；脚本会查找目录内唯一 `.uproject` |
| PIE 测试在 `-nullrhi` 下异常 | 用 `--no-null-rhi` 重跑同一 scope |

## 报告位置

测试报告生成于项目目录：
```
Saved/
└── Automation/
    ├── autotest_results.json          # 结构化结果
    └── Reports/
        ├── Raw/<Scope>/               # UE 原生 Automation report 输出（按运行 scope 命名）
        └── YYYY-MM-DD-HHmmss-autotest-report.md
```

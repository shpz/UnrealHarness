---
name: ue-build
description: >
  编译 Unreal Engine 5 C++ 项目。
  当用户提到以下任何内容时触发此技能：UE5编译、Unreal Engine构建、
  编译.uproject项目、C++编译、"build unreal engine"、"compile UE5 C++"、
  "编译项目"、"ue5 build"，或任何涉及 UnrealBuildTool 的工作流。
  默认编译 Development Editor 配置，除非用户明确要求 debug/调试。
  此技能仅执行编译，不修改任何源代码。
---

# UE5 编译 Skill

## 用途

通过 UnrealBuildTool (UBT) 编译 Unreal Engine 5 C++ 项目。

## 何时使用

- 用户想要编译或构建 UE5 项目
- 用户在 UE5 上下文中提到"编译"、"build"、"compile"

## 前置条件

项目目录必须包含 `.uproject` 文件。如果当前目录没有，向用户询问正确的项目路径。

## 执行流程

### 步骤 1：确认项目路径

检查当前工作目录中是否有 `.uproject` 文件。如果没有，提示用户提供项目路径。

### 步骤 2：确定编译配置

根据用户提示词选择配置：

| 提示词包含 | 配置 |
|-----------|------|
| （默认） | Development Editor |
| "debug"、"debugging"、"Debug"、"调试" | Debug Editor |

### 步骤 3：查找引擎路径

先调用 `find-engine.ps1` 自动查找引擎：

```bash
powershell -File "<skill-root>/find-engine.ps1" -ProjectPath "<项目路径>"
```

**如果找到引擎**：记录引擎路径，传给 `build.ps1`。

**如果未找到引擎**：
1. 向用户说明：无法自动找到与项目关联的 Unreal Engine
2. 询问用户引擎安装路径（例如 `C:\Program Files\Epic Games\UE_5.4`）
3. 用户确认路径后，传给 `build.ps1`

### 步骤 4：调用编译脚本

执行 PowerShell 脚本，传入引擎路径：

```bash
powershell -File "<skill-root>/build.ps1" -ProjectPath "<项目路径>" -Configuration "<配置>" -EnginePath "<引擎路径>"
```

### 步骤 5：检查执行结果

脚本返回 exit code：
- **0**：编译成功，向用户确认
- **非 0**：编译失败，分析 stderr/stdout 判断错误类型

### 步骤 6：失败类型判断与重试（Agent 层）

| 错误特征 | 处理方式 |
|---------|---------|
| 包含 "cannot access"、"being used by another process"、"The process cannot access" | 偶发性错误，可重试（最多 3 次） |
| 包含 "cannot find the file"（指 UBT 本身未找到） | 可重试（最多 3 次） |
| 包含 "error C"、"error LNK"、"fatal error" | 编译错误，直接报告用户，**不重试** |
| 其他编译相关错误 | 直接报告用户，**不重试** |

**最大重试次数：3 次**。每次重试用相同的参数重新调用 `build.ps1`。

### 步骤 7：反馈结果

- **成功**：告知用户编译配置和成功状态
- **编译错误**：呈现 UBT 原始错误输出，帮助用户定位问题
- **偶发性错误重试后仍失败**：告知用户可能的外部环境问题（如文件锁）

## 限制

- 仅支持 Windows (Win64) 平台
- 仅执行编译，不自动修复任何代码错误
- 需要安装 Epic Games Launcher 或正确注册源码编译的引擎

## 脚本参考

| 文件 | 用途 |
|------|------|
| `find-engine.ps1` | 查找引擎 — 从 .uproject 和注册表定位引擎安装目录 |
| `build.ps1` | 编译入口 — 需要传入 -EnginePath |

`find-engine.ps1` 可独立运行用于调试。`build.ps1` 是编译的唯一入口。

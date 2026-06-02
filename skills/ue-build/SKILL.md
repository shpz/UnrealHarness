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

## 执行流程

### 步骤 1：确认项目路径

检查当前工作目录中是否有 `.uproject` 文件：
- 单个 → 自动使用
- 多个 → 提示用户指定
- 无 → 询问项目路径

### 步骤 2：确定编译配置

根据用户提示词选择配置：

| 提示词包含 | 配置 |
|-----------|------|
| （默认） | Development |
| "debug"、"debugging"、"Debug"、"调试" | Debug |

### 步骤 3：调用编译脚本

执行 PowerShell 脚本：

```bash
powershell -File "<skill-root>/build.ps1" -ProjectPath "<项目路径>" -Configuration "<配置>"
```

脚本会自动：
- 从 `.uproject` 的 `EngineAssociation` 解析引擎路径
- 推导 Target 名称（`项目名Editor`）
- 调用 UBT 执行编译

### 步骤 4：检查执行结果

脚本返回 exit code：
- **0**：编译成功，向用户确认
- **非 0**：编译失败，分析 stderr/stdout 判断错误类型

### 步骤 5：失败类型判断与重试（Agent 层）

| 错误特征 | 处理方式 |
|---------|---------|
| 包含 "cannot access"、"being used by another process"、"The process cannot access" | 偶发性错误，可重试（最多 3 次） |
| 包含 "cannot find the file"（指 UBT 本身未找到） | 可重试（最多 3 次） |
| 包含 "error C"、"error LNK"、"fatal error" | 编译错误，直接报告用户，**不重试** |
| 其他编译相关错误 | 直接报告用户，**不重试** |

**最大重试次数：3 次**。每次重试用相同的参数重新调用 `build.ps1`。

### 步骤 6：反馈结果

- **成功**：告知用户编译配置和成功状态
- **编译错误**：呈现 UBT 原始错误输出，帮助用户定位问题
- **偶发性错误重试后仍失败**：告知用户可能的外部环境问题（如文件锁）
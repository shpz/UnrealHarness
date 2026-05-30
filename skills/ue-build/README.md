# UE5 编译 Skill

用于编译 Unreal Engine 5 C++ 项目的 Claude Code Skill。

## 功能

- **直接调用 UBT**：通过 UnrealBuildTool 编译项目
- **默认 Development Editor**：提示词含 debug 时切换为 Debug Editor
- **Agent 层重试**：偶发性错误（文件锁等）可由 Claude 重试最多 3 次

## 安装

确保目录结构：
```
~/.claude/skills/ue-build/
├── SKILL.md
├── build.ps1
├── config.yaml
└── README.md
```

安装完成，Claude Code 会自动识别该 Skill。

## 使用方法

### 在 Claude Code 中使用

```
# 默认 Development Editor 编译
编译 UE5 项目

# Debug Editor 编译
debug 编译项目
调试模式编译

# 指定项目路径
编译 D:\\MyProject
```

### 命令行使用

```powershell
# 当前目录项目，默认 Development Editor
.\build.ps1

# 指定项目路径
.\build.ps1 -ProjectPath "C:\\MyProject"

# Debug 编译
.\build.ps1 -ProjectPath "C:\\MyProject" -Configuration "Debug Editor"
```

## 配置

编辑 `config.yaml`：

```yaml
build:
  defaultConfiguration: Development Editor
  debugKeywords:
    - debug
    - debugging
    - Debug
    - 调试
  platform: Win64
  timeoutMinutes: 30
```

## 环境要求

- Windows 操作系统
- PowerShell
- 已安装 Unreal Engine 5
- 引擎已通过 Epic Games Launcher 安装或正确注册

## 工作原理

1. **项目验证**：检查 `.uproject` 文件
2. **查找 UBT**：从 `.uproject` 关联的引擎路径查找 `UnrealBuildTool.exe`
3. **执行编译**：直接调用 UBT，stdout/stderr 原样透传
4. **返回结果**：exit code 0 表示成功，非 0 表示失败

## 限制

- 仅支持 Windows (Win64) 平台
- 不自动修复代码错误
- 需要正确配置 UE5 环境

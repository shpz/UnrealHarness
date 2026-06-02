#Requires -Version 5.1
<#
.SYNOPSIS
    通用 Unreal Engine 5 项目编译脚本
.DESCRIPTION
    自动检测项目文件、解析引擎路径并编译 UE5 C++ 项目
    支持 Launcher 安装和源码编译引擎
.PARAMETER ProjectPath
    .uproject 文件路径（可选，默认自动检测当前目录）
.PARAMETER Configuration
    编译配置: Development (默认), Debug, Shipping, Test
.PARAMETER Platform
    目标平台: Win64 (默认)
.EXAMPLE
    .\build.ps1
    .\build.ps1 -Configuration Debug
    .\build.ps1 -ProjectPath "D:\Projects\MyGame\MyGame.uproject"
#>
param(
    [string]$ProjectPath = "",

    [ValidateSet("Development", "Debug", "Shipping", "Test")]
    [string]$Configuration = "Development",

    [ValidateSet("Win64")]
    [string]$Platform = "Win64"
)

$ErrorActionPreference = "Stop"

# ============================================
# 1. 项目发现
# ============================================
function Find-ProjectFile {
    param([string]$ExplicitPath)

    if ($ExplicitPath -and (Test-Path $ExplicitPath)) {
        return (Resolve-Path $ExplicitPath).Path
    }

    $uprojectFiles = Get-ChildItem -Path "." -Filter "*.uproject" -File

    if ($uprojectFiles.Count -eq 0) {
        Write-Error "当前目录未找到 .uproject 文件。请提供项目路径: -ProjectPath `"路径\项目.uproject`""
        exit 1
    }

    if ($uprojectFiles.Count -eq 1) {
        return $uprojectFiles[0].FullName
    }

    # 多个项目，列出供选择
    Write-Host "发现多个 UE5 项目:" -ForegroundColor Yellow
    for ($i = 0; $i -lt $uprojectFiles.Count; $i++) {
        Write-Host "  [$i] $($uprojectFiles[$i].Name)" -ForegroundColor Cyan
    }
    Write-Host "请使用 -ProjectPath 参数指定要编译的项目" -ForegroundColor Yellow
    exit 1
}

# ============================================
# 2. 引擎路径解析
# ============================================
function Resolve-EnginePath {
    param([string]$ProjectFile)

    # 读取 .uproject 的 EngineAssociation
    $uprojectContent = Get-Content $ProjectFile -Raw | ConvertFrom-Json
    $engineAssociation = $uprojectContent.EngineAssociation

    if (-not $engineAssociation) {
        Write-Error "无法从 .uproject 读取 EngineAssociation 字段"
        exit 1
    }

    $enginePath = $null

    # 判断是版本号还是 GUID
    if ($engineAssociation -match '^\d+\.\d+$') {
        # Launcher 安装的引擎: 从注册表读取
        $regPath = "HKLM:\SOFTWARE\EpicGames\Unreal Engine\$engineAssociation"
        try {
            $enginePath = (Get-ItemProperty -Path $regPath -ErrorAction Stop).InstalledDirectory
        } catch {
            Write-Error "未找到 UE $engineAssociation 的注册表项。请确认已通过 Epic Games Launcher 安装。"
            exit 1
        }
    } else {
        # 源码编译引擎: GUID 格式
        $regPath = "HKCU:\SOFTWARE\Epic Games\Unreal Engine\Builds\$engineAssociation"
        try {
            $enginePath = (Get-ItemProperty -Path $regPath -ErrorAction Stop).Path
        } catch {
            Write-Error "未找到源码编译引擎的注册表项。请确认引擎已正确注册。"
            exit 1
        }
    }

    if (-not (Test-Path $enginePath)) {
        Write-Error "引擎路径不存在: $enginePath"
        exit 1
    }

    return $enginePath
}

# ============================================
# 3. Target 推导
# ============================================
function Get-BuildTarget {
    param([string]$ProjectFile)

    $projectName = [System.IO.Path]::GetFileNameWithoutExtension($ProjectFile)
    return "${projectName}Editor"
}

# ============================================
# 主流程
# ============================================
$projectFile = Find-ProjectFile -ExplicitPath $ProjectPath
$enginePath = Resolve-EnginePath -ProjectFile $projectFile
$target = Get-BuildTarget -ProjectFile $projectFile

$buildBat = Join-Path $enginePath "Engine\Build\BatchFiles\Build.bat"
if (-not (Test-Path $buildBat)) {
    Write-Error "未找到 Build.bat: $buildBat"
    exit 1
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Unreal Engine 5 项目编译" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "项目: $projectFile"
Write-Host "目标: $target"
Write-Host "平台: $Platform"
Write-Host "配置: $Configuration"
Write-Host "引擎: $enginePath"
Write-Host "============================================" -ForegroundColor Cyan

# 执行编译
& $buildBat $target $Platform $Configuration "$projectFile" -waitmutex

if ($LASTEXITCODE -ne 0) {
    Write-Error "编译失败，退出码: $LASTEXITCODE"
    exit $LASTEXITCODE
}

Write-Host "============================================" -ForegroundColor Green
Write-Host "编译成功!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green

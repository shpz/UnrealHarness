<#
.SYNOPSIS
    Compile Unreal Engine 5 C++ project (single-shot, no retry, no fix)

.DESCRIPTION
    Execute a single UBT compilation. Requires -EnginePath to be provided.
    stdout/stderr pass through as-is, return exit code.

.PARAMETER ProjectPath
    Project root directory (must contain .uproject file). Defaults to current directory.

.PARAMETER Configuration
    Build compilation. Defaults to "Development Editor".

.PARAMETER Platform
    Target platform. Defaults to "Win64".

.PARAMETER EnginePath
    Engine root directory (required). Use find-engine.ps1 to locate it before calling this script.
#>
[CmdletBinding()]
param(
    [string]$ProjectPath = $PWD,
    [string]$Configuration = "Development Editor",
    [string]$Platform = "Win64",
    [string]$EnginePath = ""
)

$ErrorActionPreference = "Stop"

# ---- UTF-8 encoding output ----
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# 1. Validate project path
$resolvedPath = Resolve-Path $ProjectPath -ErrorAction SilentlyContinue
if (-not $resolvedPath) {
    Write-Error "Project path does not exist: $ProjectPath"
    exit 1
}

# 2. Find .uproject file
$uprojectFiles = Get-ChildItem -Path $resolvedPath -Filter "*.uproject" -File
if ($uprojectFiles.Count -eq 0) {
    Write-Error "No .uproject file found in '$resolvedPath'"
    exit 1
}
if ($uprojectFiles.Count -gt 1) {
    Write-Error "Multiple .uproject files found in '$resolvedPath'. Please ensure only one project file exists."
    exit 1
}

$uprojectFile = $uprojectFiles[0]
$projectName = [System.IO.Path]::GetFileNameWithoutExtension($uprojectFile.Name)

# 3. Resolve UBT path from EnginePath
if (-not $EnginePath) {
    Write-Error "EnginePath is required. Use find-engine.ps1 to locate the engine before calling build.ps1."
    exit 1
}

# UE5.4+ UBT path changed: Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.exe
$ubtPathNew = Join-Path $EnginePath "Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.exe"
$ubtPathLegacy = Join-Path $EnginePath "Engine\Binaries\DotNET\UnrealBuildTool.exe"

$ubtPath = $null
if (Test-Path $ubtPathNew) {
    $ubtPath = $ubtPathNew
} elseif (Test-Path $ubtPathLegacy) {
    $ubtPath = $ubtPathLegacy
} else {
    Write-Error "UnrealBuildTool.exe not found at expected paths:`n  - $ubtPathNew`n  - $ubtPathLegacy"
    exit 1
}

# 4. Parse "Development Editor" / "Debug Editor" into UBT-compatible Target and Configuration
# UBT expects: <TargetName> <Platform> <Configuration>
# "Editor" is part of TargetName, NOT Configuration
$ubtTarget = $projectName
$ubtConfiguration = "Development"

if ($Configuration -match "Editor") {
    $ubtTarget = "${projectName}Editor"
}
if ($Configuration -match "Debug") {
    $ubtConfiguration = "Debug"
} elseif ($Configuration -match "Development") {
    $ubtConfiguration = "Development"
} elseif ($Configuration -match "Shipping") {
    $ubtConfiguration = "Shipping"
} elseif ($Configuration -match "Test") {
    $ubtConfiguration = "Test"
}

# 5. Assemble and execute UBT command
# Use separate array elements for -Project and path to handle spaces correctly
$ubtArgs = @(
    $ubtTarget,
    $ubtConfiguration,
    $Platform,
    "-Project",
    $uprojectFile.FullName
)

Write-Host "Project: $($uprojectFile.FullName)"
Write-Host "Target: $ubtTarget"
Write-Host "Configuration: $ubtConfiguration"
Write-Host "Platform: $Platform"
Write-Host "UBT: $ubtPath"
Write-Host ""

$process = Start-Process -FilePath $ubtPath -ArgumentList $ubtArgs -NoNewWindow -Wait -PassThru
exit $process.ExitCode

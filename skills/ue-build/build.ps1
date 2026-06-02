#Requires -Version 5.1
<#
.SYNOPSIS
    Generic Unreal Engine 5 project build script
.DESCRIPTION
    Auto-detect project file, resolve engine path, and build UE5 C++ project.
    Supports both Launcher-installed and source-built engines.
.PARAMETER ProjectPath
    Path to .uproject file (optional, auto-detects from current directory)
.PARAMETER Configuration
    Build configuration: Development (default), Debug, Shipping, Test
.PARAMETER Platform
    Target platform: Win64 (default)
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
# 1. Project Discovery
# ============================================
function Find-ProjectFile {
    param([string]$ExplicitPath)

    if ($ExplicitPath -and (Test-Path $ExplicitPath)) {
        return (Resolve-Path $ExplicitPath).Path
    }

    $uprojectFiles = Get-ChildItem -Path "." -Filter "*.uproject" -File

    if ($uprojectFiles.Count -eq 0) {
        Write-Error "No .uproject file found in current directory. Please provide project path: -ProjectPath `"path\project.uproject`""
        exit 1
    }

    if ($uprojectFiles.Count -eq 1) {
        return $uprojectFiles[0].FullName
    }

    # Multiple projects found, list them
    Write-Host "Multiple UE5 projects found:" -ForegroundColor Yellow
    for ($i = 0; $i -lt $uprojectFiles.Count; $i++) {
        Write-Host "  [$i] $($uprojectFiles[$i].Name)" -ForegroundColor Cyan
    }
    Write-Host "Please use -ProjectPath parameter to specify which project to build" -ForegroundColor Yellow
    exit 1
}

# ============================================
# 2. Engine Path Resolution
# ============================================
function Resolve-EnginePath {
    param([string]$ProjectFile)

    # Read EngineAssociation from .uproject
    $uprojectContent = Get-Content $ProjectFile -Raw | ConvertFrom-Json
    $engineAssociation = $uprojectContent.EngineAssociation

    if (-not $engineAssociation) {
        Write-Error "Failed to read EngineAssociation field from .uproject"
        exit 1
    }

    $enginePath = $null

    # Determine if it's a version number or GUID
    if ($engineAssociation -match '^\d+\.\d+$') {
        # Launcher-installed engine: read from registry
        $regPath = "HKLM:\SOFTWARE\EpicGames\Unreal Engine\$engineAssociation"
        try {
            $enginePath = (Get-ItemProperty -Path $regPath -ErrorAction Stop).InstalledDirectory
        } catch {
            Write-Error "UE $engineAssociation registry entry not found. Please verify installation via Epic Games Launcher."
            exit 1
        }
    } else {
        # Source-built engine: GUID format
        $regPath = "HKCU:\SOFTWARE\Epic Games\Unreal Engine\Builds\$engineAssociation"
        try {
            $enginePath = (Get-ItemProperty -Path $regPath -ErrorAction Stop).Path
        } catch {
            Write-Error "Source-built engine registry entry not found. Please verify engine is properly registered."
            exit 1
        }
    }

    if (-not (Test-Path $enginePath)) {
        Write-Error "Engine path does not exist: $enginePath"
        exit 1
    }

    return $enginePath
}

# ============================================
# 3. Target Derivation
# ============================================
function Get-BuildTarget {
    param([string]$ProjectFile)

    $projectName = [System.IO.Path]::GetFileNameWithoutExtension($ProjectFile)
    return "${projectName}Editor"
}

# ============================================
# Main Flow
# ============================================
$projectFile = Find-ProjectFile -ExplicitPath $ProjectPath
$enginePath = Resolve-EnginePath -ProjectFile $projectFile
$target = Get-BuildTarget -ProjectFile $projectFile

$buildBat = Join-Path $enginePath "Engine\Build\BatchFiles\Build.bat"
if (-not (Test-Path $buildBat)) {
    Write-Error "Build.bat not found: $buildBat"
    exit 1
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Unreal Engine 5 Project Build" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Project: $projectFile"
Write-Host "Target:  $target"
Write-Host "Platform: $Platform"
Write-Host "Configuration: $Configuration"
Write-Host "Engine:  $enginePath"
Write-Host "============================================" -ForegroundColor Cyan

# Execute build
& $buildBat $target $Platform $Configuration "$projectFile" -waitmutex

if ($LASTEXITCODE -ne 0) {
    Write-Error "Build failed with exit code: $LASTEXITCODE"
    exit $LASTEXITCODE
}

Write-Host "============================================" -ForegroundColor Green
Write-Host "Build succeeded!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green

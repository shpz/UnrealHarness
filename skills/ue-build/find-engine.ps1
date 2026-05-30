<#
.SYNOPSIS
    Find the Unreal Engine installation associated with a .uproject file.

.DESCRIPTION
    Reads EngineAssociation from .uproject, then looks up the engine path in registry.
    Supports both Launcher-installed versions and source-built engines.

.PARAMETER ProjectPath
    Project root directory containing a .uproject file.

.OUTPUTS
    Engine root directory path (e.g. "C:\Program Files\Epic Games\UE_5.5")
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectPath
)

$ErrorActionPreference = "Stop"

# ---- UTF-8 encoding output ----
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# 1. Find .uproject file
$resolvedPath = Resolve-Path $ProjectPath -ErrorAction SilentlyContinue
if (-not $resolvedPath) {
    Write-Error "Project path does not exist: $ProjectPath"
    exit 1
}

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

# 2. Read EngineAssociation from .uproject
$uprojectContent = Get-Content $uprojectFile.FullName -Raw
# Strip single-line comments before JSON parse (some .uproject files may contain // comments)
$uprojectContent = [regex]::Replace($uprojectContent, '(?m)^\s*//.*$', '')
$uprojectJson = $uprojectContent | ConvertFrom-Json
$engineAssociation = $uprojectJson.EngineAssociation

# 3. Look up engine path based on EngineAssociation
$engineDir = $null

# 3a. Launcher-installed version (e.g. "5.5", "5.4")
if ($engineAssociation -match '^\d+\.\d+$') {
    # Try registry first
    $regPath = "HKLM:\SOFTWARE\EpicGames\Unreal Engine\$engineAssociation"
    if (Test-Path $regPath) {
        $engineDir = (Get-ItemProperty $regPath -Name "InstalledDirectory" -ErrorAction SilentlyContinue).InstalledDirectory
    }

    # Fallback to default install paths
    if (-not $engineDir) {
        $defaultPaths = @(
            "C:\Program Files\Epic Games\UE_$engineAssociation",
            "C:\Program Files (x86)\Epic Games\UE_$engineAssociation",
            "D:\Epic Games\UE_$engineAssociation"
        )
        foreach ($path in $defaultPaths) {
            if (Test-Path $path) {
                $engineDir = $path
                break
            }
        }
    }
}
# 3b. Source-built engine (GUID format)
elseif ($engineAssociation -and ($engineAssociation -match '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')) {
    $regPath = "HKCU:\Software\Epic Games\Unreal Engine\Builds"
    if (Test-Path $regPath) {
        $buildEntry = Get-ItemProperty $regPath -Name $engineAssociation -ErrorAction SilentlyContinue
        if ($buildEntry) {
            # Use PSObject.Properties to safely access properties with hyphens (GUID format)
            $prop = $buildEntry.PSObject.Properties[$engineAssociation]
            if ($prop) {
                $engineDir = $prop.Value
            }
        }
    }
}
# 3c. Empty or missing EngineAssociation — find newest UE5
if (-not $engineDir) {
    # Try registry for any installed version
    $regPath = "HKLM:\SOFTWARE\EpicGames\Unreal Engine"
    if (Test-Path $regPath) {
        $versions = Get-ChildItem $regPath -ErrorAction SilentlyContinue | Where-Object {
            $_.PSChildName -match '^\d+\.\d+$'
        } | Sort-Object {
            [version]$_.PSChildName
        } -Descending

        foreach ($ver in $versions) {
            $dir = (Get-ItemProperty $ver.PSPath -Name "InstalledDirectory" -ErrorAction SilentlyContinue).InstalledDirectory
            if ($dir -and (Test-Path $dir)) {
                $engineDir = $dir
                break
            }
        }
    }

    # Fallback: scan default paths for UE_5.*
    if (-not $engineDir) {
        $patterns = @(
            "C:\Program Files\Epic Games\UE_5.*",
            "C:\Program Files (x86)\Epic Games\UE_5.*",
            "D:\Epic Games\UE_5.*"
        )
        foreach ($pattern in $patterns) {
            $found = Get-Item -Path $pattern -ErrorAction SilentlyContinue |
                Where-Object { $_.PSIsContainer } |
                Sort-Object Name -Descending |
                Select-Object -First 1
            if ($found) {
                $engineDir = $found.FullName
                break
            }
        }
    }
}

# 4. Fallback: parse .sln file to infer engine path
if (-not $engineDir) {
    # Look for .sln in project directory or parent directories
    $searchPath = $resolvedPath
    $slnFile = $null
    for ($i = 0; $i -lt 3; $i++) {
        $candidates = Get-ChildItem -Path $searchPath -Filter "*.sln" -File -ErrorAction SilentlyContinue
        if ($candidates) {
            $slnFile = $candidates | Select-Object -First 1
            break
        }
        $parent = Split-Path -Parent $searchPath
        if (-not $parent -or $parent -eq $searchPath) { break }
        $searchPath = $parent
    }

    if ($slnFile) {
        # Parse .sln for UnrealBuildTool.csproj path
        $content = Get-Content $slnFile.FullName -Raw
        $pattern = 'UnrealBuildTool\.csproj"\s*,\s*"([^"]+)"'
        $match = [regex]::Match($content, $pattern)
        if ($match.Success) {
            $csprojPath = $match.Groups[1].Value
            # Derive engine root from: .../Engine/Source/Programs/UnrealBuildTool/UnrealBuildTool.csproj
            $engineMatch = [regex]::Match($csprojPath, '^(.*?)\\Engine\\Source\\Programs\\UnrealBuildTool')
            if ($engineMatch.Success) {
                $inferredDir = $engineMatch.Groups[1].Value
                if (Test-Path $inferredDir) {
                    $engineDir = $inferredDir
                }
            }
        }
    }
}

if (-not $engineDir -or -not (Test-Path $engineDir)) {
    Write-Error "Could not find the Unreal Engine associated with this project. Project: $($uprojectFile.FullName), EngineAssociation: $engineAssociation. Please ensure the corresponding engine version is installed via Epic Games Launcher, or the source-built engine is properly registered."
    exit 1
}

Write-Output $engineDir

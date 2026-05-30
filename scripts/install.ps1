#requires -Version 5.1
<#
.SYNOPSIS
    Install UnrealHarness skills into AI assistant skills directories.

.DESCRIPTION
    Scans the project skills/ folder and copies or symlinks each skill
    to the target AI assistant's skills directory.
    Supports Claude Code, OpenCode, Codex, and Kimi Code.

.PARAMETER Assistant
    Target AI assistant: claude, opencode, codex, kimi, or all (default).

.PARAMETER Link
    Create symbolic links instead of copying files. Useful for development.

.PARAMETER Force
    Overwrite existing skill directories.

.EXAMPLE
    .\install-skills.ps1
    # Install to all detected assistants

.EXAMPLE
    .\install-skills.ps1 -Assistant claude -Link
    # Symlink to Claude Code only
#>
[CmdletBinding()]
param(
    [ValidateSet("claude","opencode","codex","kimi","all")]
    [string]$Assistant = "all",

    [switch]$Link,

    [switch]$Force
)

$ErrorActionPreference = "Stop"

# ---- Paths ----
$scriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$skillsDir   = Join-Path $projectRoot "skills"

$configs = @{
    claude   = @{ Name = "Claude Code"; Path = Join-Path $env:USERPROFILE ".claude\skills" }
    opencode = @{ Name = "OpenCode";    Path = Join-Path $env:USERPROFILE ".opencode\skills" }
    codex    = @{ Name = "Codex";       Path = Join-Path $env:USERPROFILE ".codex\skills" }
    kimi     = @{ Name = "Kimi Code";   Path = Join-Path $env:USERPROFILE ".kimi\skills" }
}

# ---- Validate source ----
if (-not (Test-Path $skillsDir)) {
    Write-Error "Skills source directory not found: $skillsDir"
    exit 1
}

$skills = Get-ChildItem -Path $skillsDir -Directory
if ($skills.Count -eq 0) {
    Write-Error "No skills found in: $skillsDir"
    exit 1
}

Write-Host "Found $($skills.Count) skill(s):" -ForegroundColor Cyan
$skills | ForEach-Object { Write-Host "  - $($_.Name)" }
Write-Host ""

# ---- Install ----
$targets = if ($Assistant -eq "all") { @("claude","opencode","codex","kimi") } else { @($Assistant) }
$installedAny = $false

foreach ($key in $targets) {
    $cfg = $configs[$key]
    $dest = $cfg.Path

    # Check if assistant is installed
    if (-not (Test-Path $dest)) {
        $parent = Split-Path -Parent $dest
        if (-not (Test-Path $parent)) {
            Write-Host "[$($cfg.Name)] not detected, skipping" -ForegroundColor DarkGray
            continue
        }
        New-Item -ItemType Directory -Path $dest -Force | Out-Null
    }

    Write-Host "[$($cfg.Name)] installing to: $dest" -ForegroundColor Green

    foreach ($skill in $skills) {
        $srcPath = $skill.FullName
        $dstPath = Join-Path $dest $skill.Name

        if (Test-Path $dstPath) {
            if (-not $Force) {
                Write-Host "  skip $($skill.Name) (exists, use -Force to overwrite)" -ForegroundColor Yellow
                continue
            }
            $item = Get-Item $dstPath
            if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                $item.Delete()
            } else {
                Remove-Item -Path $dstPath -Recurse -Force
            }
        }

        if ($Link) {
            $null = New-Item -ItemType SymbolicLink -Path $dstPath -Target $srcPath
            Write-Host "  link $($skill.Name) -> $srcPath" -ForegroundColor Cyan
        } else {
            Copy-Item -Path $srcPath -Destination $dstPath -Recurse -Force
            Write-Host "  copy $($skill.Name)" -ForegroundColor Cyan
        }

        $installedAny = $true
    }

    Write-Host ""
}

if (-not $installedAny) {
    Write-Host "Nothing was installed. Make sure the target assistant is installed or use -Assistant." -ForegroundColor Red
    exit 1
}

Write-Host "Done." -ForegroundColor Green

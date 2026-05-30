#requires -Version 5.1
<#
.SYNOPSIS
    Uninstall UnrealHarness skills from AI assistant skills directories.

.DESCRIPTION
    Removes skills that match this project's skills/ folder from the target
    AI assistant's skills directory.

.PARAMETER Assistant
    Target AI assistant: claude, opencode, codex, or all (default).

.PARAMETER Force
    Skip confirmation prompt.

.EXAMPLE
    .\uninstall-skills.ps1
    # Uninstall from all detected assistants

.EXAMPLE
    .\uninstall-skills.ps1 -Assistant claude -Force
    # Remove from Claude Code without prompting
#>
[CmdletBinding()]
param(
    [ValidateSet("claude","opencode","codex","all")]
    [string]$Assistant = "all",

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
}

# ---- Validate source ----
if (-not (Test-Path $skillsDir)) {
    Write-Error "Skills source directory not found: $skillsDir"
    exit 1
}

$skills = Get-ChildItem -Path $skillsDir -Directory | Select-Object -ExpandProperty Name
if ($skills.Count -eq 0) {
    Write-Error "No skills found in: $skillsDir"
    exit 1
}

# ---- Determine targets ----
$targets = if ($Assistant -eq "all") { @("claude","opencode","codex") } else { @($Assistant) }
$toRemove = @()

foreach ($key in $targets) {
    $cfg = $configs[$key]
    $dest = $cfg.Path
    if (-not (Test-Path $dest)) {
        Write-Host "[$($cfg.Name)] not detected, skipping" -ForegroundColor DarkGray
        continue
    }

    foreach ($skill in $skills) {
        $skillPath = Join-Path $dest $skill
        if (Test-Path $skillPath) {
            $toRemove += [PSCustomObject]@{
                Assistant = $cfg.Name
                Skill     = $skill
                Path      = $skillPath
            }
        }
    }
}

if ($toRemove.Count -eq 0) {
    Write-Host "No matching skills found to uninstall." -ForegroundColor Yellow
    exit 0
}

# ---- Preview ----
Write-Host "The following will be removed:" -ForegroundColor Yellow
$toRemove | ForEach-Object {
    Write-Host "  [$($_.Assistant)] $($_.Skill)" -ForegroundColor Cyan
}

# ---- Confirm ----
if (-not $Force) {
    $confirm = Read-Host "Proceed? (y/N)"
    if ($confirm -notmatch '^[Yy]$') {
        Write-Host "Aborted." -ForegroundColor Yellow
        exit 0
    }
}

# ---- Remove ----
$removedAny = $false
foreach ($item in $toRemove) {
    $path = $item.Path
    $skillItem = Get-Item $path
    if ($skillItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        $skillItem.Delete()
    } else {
        Remove-Item -Path $path -Recurse -Force
    }
    Write-Host "Removed [$($item.Assistant)] $($item.Skill)" -ForegroundColor Green
    $removedAny = $true
}

if ($removedAny) {
    Write-Host "Done." -ForegroundColor Green
}

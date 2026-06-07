#Requires -Version 5.1
<#
.SYNOPSIS
    UE5 Automation Test Runner
.DESCRIPTION
    Scans test modules, builds project via ue-build, runs tests via UnrealEditor-Cmd,
    parses logs, and outputs structured results.
.PARAMETER ProjectPath
    Path to project directory or .uproject file (optional, auto-detects)
.PARAMETER Scope
    Test scope: "all", module name, or wildcard pattern like "MyProject.AI.*"
.PARAMETER Configuration
    Build configuration: Development (default), Debug
.EXAMPLE
    .\autotest.ps1
    .\autotest.ps1 -Scope "CoreGameplayTest"
    .\autotest.ps1 -ProjectPath "D:\Projects\MyGame\MyGame.uproject" -Scope "all"
#>
param(
    [string]$ProjectPath = "",
    [string]$Scope = "all",
    [ValidateSet("Development", "Debug")]
    [string]$Configuration = "Development",
    [switch]$NoNullRHI
)

$ErrorActionPreference = "Stop"
$script:IsDotSourced = $MyInvocation.InvocationName -eq "."

# Resolve script location for relative paths
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillRoot = Split-Path -Parent $scriptDir

# Load config
$configPath = Join-Path $skillRoot "config.yaml"
if (-not (Test-Path $configPath)) {
    Write-Error "Config file not found: $configPath"
    exit 1
}
# Parse YAML manually — PowerShell 5.1 has no built-in YAML parser.
# If powershell-yaml module is available, use it; otherwise fall back to hardcoded defaults.
$config = @{
    testModulePattern = "Source/*Test/*.Build.cs"
    editorTimeoutSeconds = 600
    reportOutputDir = "Saved/Automation/Reports"
    editorExtraArgs = @("-unattended", "-nopause", "-nosplash", "-log")
    logPatterns = @{
        testPassed = 'LogAutomationController:\s+(.+?)\s+passed\s*\(([^)]+)\)'
        testFailed = 'LogAutomationController:\s+(.+?)\s+failed'
        testError = 'LogAutomationController:\s*Error:\s*(.+)'
    }
}
# TODO: Add YAML parsing if powershell-yaml module becomes a dependency.

# ============================================
# 1. Project Discovery
# ============================================
function Find-ProjectFile {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        $resolvedPath = Resolve-Path $ExplicitPath -ErrorAction SilentlyContinue
        if (-not $resolvedPath) {
            throw "Project path does not exist: $ExplicitPath"
        }

        $item = Get-Item -LiteralPath $resolvedPath.Path
        if (-not $item.PSIsContainer) {
            if ($item.Extension -ne ".uproject") {
                throw "ProjectPath must be a project directory or .uproject file: $ExplicitPath"
            }
            return $item.FullName
        }

        $uprojectFiles = Get-ChildItem -LiteralPath $item.FullName -Filter "*.uproject" -File
        if ($uprojectFiles.Count -eq 0) {
            throw "No .uproject file found in '$($item.FullName)'"
        }
        if ($uprojectFiles.Count -gt 1) {
            throw "Multiple .uproject files found in '$($item.FullName)'. Use -ProjectPath to specify the .uproject file."
        }
        return $uprojectFiles[0].FullName
    }

    $uprojectFiles = Get-ChildItem -LiteralPath "." -Filter "*.uproject" -File
    if ($uprojectFiles.Count -eq 0) {
        throw "No .uproject file found. Use -ProjectPath to specify."
    }
    if ($uprojectFiles.Count -eq 1) {
        return $uprojectFiles[0].FullName
    }
    throw "Multiple .uproject files found. Use -ProjectPath to specify."
}

# ============================================
# 2. Scan Test Modules
# ============================================
function Get-TestModules {
    param([string]$ProjectDir, [string]$Pattern)

    $searchPath = Join-Path $ProjectDir $Pattern
    $buildCsFiles = Get-ChildItem -Path $searchPath -ErrorAction SilentlyContinue

    $modules = @()
    foreach ($file in $buildCsFiles) {
        $moduleName = $file.Name -replace '\.Build\.cs$', ''
        $modules += $moduleName
    }
    return $modules
}

# ============================================
# 3. Filter Modules by Scope
# ============================================
function Test-ScopeMatchesPrefix {
    param([string]$Scope, [string]$Prefix)

    $normalizedScope = $Scope.TrimEnd('*').TrimEnd('.')
    $normalizedPrefix = $Prefix.TrimEnd('*').TrimEnd('.')

    if ($normalizedScope -eq $normalizedPrefix) { return $true }
    if ($normalizedScope -eq ($normalizedPrefix.Split('.')[0])) { return $true }
    if ($normalizedPrefix.StartsWith("$normalizedScope.")) { return $true }
    if ($normalizedScope.StartsWith("$normalizedPrefix.")) { return $true }
    return $false
}

function Filter-Modules {
    param([array]$Modules, [string]$Scope, [string]$ProjectDir)

    if ($Scope -eq "all") {
        return $Modules
    }

    # Check if scope matches a module name exactly
    if ($Modules -contains $Scope) {
        return @($Scope)
    }

    # Prefix-based matching: scope can be a prefix of the module's test prefix,
    # or vice versa. E.g. scope "MyProject" matches module "MyProjectTest"
    # (prefix "MyProject"); scope "MyProject.AI" also matches (starts with).
    $candidates = @()
    foreach ($mod in $Modules) {
        $prefix = $mod -replace 'Test$', ''
        $automationPrefix = Get-ModuleAutomationPrefix -ProjectDir $ProjectDir -ModuleName $mod
        if ((Test-ScopeMatchesPrefix -Scope $Scope -Prefix $prefix) -or
            (Test-ScopeMatchesPrefix -Scope $Scope -Prefix $automationPrefix)) {
            $candidates += [PSCustomObject]@{ Name = $mod; PrefixLength = $automationPrefix.Length }
        }
    }

    $filtered = @()
    if ($candidates.Count -gt 0) {
        $maxPrefixLength = ($candidates | Measure-Object -Property PrefixLength -Maximum).Maximum
        $filtered = $candidates | Where-Object { $_.PrefixLength -eq $maxPrefixLength } | ForEach-Object { $_.Name }
    }

    if ($filtered.Count -eq 0) {
        # Fallback: try wildcard match on module name itself
        $filtered = $Modules | Where-Object { $_ -like $Scope }
    }

    return $filtered
}

# ============================================
# 4. Discover Automation Test Prefix
# ============================================
function Get-ModuleAutomationPrefix {
    param([string]$ProjectDir, [string]$ModuleName)

    $moduleDir = Join-Path $ProjectDir "Source\$ModuleName"
    if (-not (Test-Path $moduleDir)) {
        $fallback = $ModuleName -replace 'Test$', ''
        return $fallback
    }

    $testNames = @()
    $sourceFiles = Get-ChildItem -LiteralPath $moduleDir -Recurse -File | Where-Object { $_.Extension -in ".cpp", ".h" }
    foreach ($file in $sourceFiles) {
        $content = Get-Content -LiteralPath $file.FullName -Raw
        $matches = [regex]::Matches(
            $content,
            'IMPLEMENT_SIMPLE_AUTOMATION_TEST\s*\([\s\S]*?,\s*"([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)"',
            [System.Text.RegularExpressions.RegexOptions]::Multiline
        )
        foreach ($match in $matches) {
            if ($match.Groups.Count -gt 1) {
                $testNames += $match.Groups[1].Value
            }
        }
    }

    if ($testNames.Count -eq 0) {
        $fallback = $ModuleName -replace 'Test$', ''
        return $fallback
    }

    $commonParts = $testNames[0].Split('.')
    foreach ($name in $testNames | Select-Object -Skip 1) {
        $parts = $name.Split('.')
        $max = [Math]::Min($commonParts.Count, $parts.Count)
        $index = 0
        while ($index -lt $max -and $commonParts[$index] -eq $parts[$index]) {
            $index++
        }
        if ($index -eq 0) {
            $commonParts = @()
            break
        }
        $commonParts = $commonParts[0..($index - 1)]
    }

    if ($commonParts.Count -eq 0) {
        return ($ModuleName -replace 'Test$', '')
    }
    return ($commonParts -join '.')
}

# ============================================
# 5. Build via ue-build
# ============================================
function Invoke-Build {
    param([string]$ProjectFile, [string]$Configuration)

    $buildScript = Join-Path $skillRoot "..\ue-build\build.ps1"
    if (-not (Test-Path $buildScript)) {
        throw "ue-build script not found: $buildScript"
    }

    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "Building project..." -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor Cyan

    $enginePath = Resolve-EnginePath -ProjectFile $ProjectFile
    $buildOutput = & powershell -File "$buildScript" -ProjectPath "$ProjectFile" -Configuration "$Configuration"
    foreach ($line in $buildOutput) {
        Write-Host $line
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Build failed with exit code $LASTEXITCODE."
    }

    return $enginePath
}

# ============================================
# 6. Derive Test Filter from Module Name
# ============================================
function Get-TestFilter {
    param([string]$ModuleName, [string]$Scope, [string]$ProjectDir)

    if ($Scope -and $Scope -ne "all" -and $Scope -ne $ModuleName) {
        return Convert-ScopeToAutomationFilter -Scope $Scope
    }

    # Module MyProjectTest -> filter MyProject.*
    # Module MyProjectAITest -> filter MyProject.AI.*
    $prefix = Get-ModuleAutomationPrefix -ProjectDir $ProjectDir -ModuleName $ModuleName
    return $prefix
}

function Convert-ScopeToAutomationFilter {
    param([string]$Scope)

    return $Scope.TrimEnd('*').TrimEnd('.')
}

# ============================================
# 7. Resolve Engine Path (reused logic from ue-build)
# ============================================
function Resolve-EnginePath {
    param([string]$ProjectFile)

    $uprojectContent = Get-Content $ProjectFile -Raw | ConvertFrom-Json
    $engineAssociation = $uprojectContent.EngineAssociation

    if (-not $engineAssociation) {
        throw "EngineAssociation not found in .uproject"
    }

    $enginePath = $null
    if ($engineAssociation -match '^\d+\.\d+$') {
        $regPath = "HKLM:\SOFTWARE\EpicGames\Unreal Engine\$engineAssociation"
        $enginePath = (Get-ItemProperty -Path $regPath -ErrorAction Stop).InstalledDirectory
    } else {
        $regPath = "HKCU:\SOFTWARE\Epic Games\Unreal Engine\Builds\$engineAssociation"
        $enginePath = (Get-ItemProperty -Path $regPath -ErrorAction Stop).Path
    }

    if (-not (Test-Path $enginePath)) {
        throw "Engine path not found: $enginePath"
    }
    return $enginePath
}

function Resolve-EditorCmd {
    param([string]$EnginePath)

    $editorCmd = Join-Path $EnginePath "Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
    if (Test-Path $editorCmd) {
        return $editorCmd
    }

    throw "UnrealEditor-Cmd.exe not found: $editorCmd"
}

# ============================================
# 8. Run Tests for a Module
# ============================================
function Run-Tests {
    param(
        [string]$ProjectFile,
        [string]$EnginePath,
        [string]$ModuleName,
        [string]$Filter,
        [hashtable]$Config,
        [switch]$NoNullRHI
    )

    $editorCmd = Resolve-EditorCmd -EnginePath $EnginePath

    $projectDir = Split-Path $ProjectFile -Parent
    $automationDir = Join-Path $projectDir "Saved\Automation"
    if (-not (Test-Path $automationDir)) {
        New-Item -ItemType Directory -Path $automationDir -Force | Out-Null
    }
    $moduleReportDir = Join-Path $automationDir ("Reports\Raw\" + $ModuleName)
    Reset-ReportDirectory -ReportDir $moduleReportDir

    $execCmds = "Automation RunTests $Filter; Quit"
    $args = @(
        "$ProjectFile",
        "-ExecCmds=`"$execCmds`"",
        "-TestExit=`"Automation Test Queue Empty`"",
        "-ReportExportPath=`"$moduleReportDir`""
    ) + $Config.editorExtraArgs

    if (-not $NoNullRHI -and -not ($args -contains "-nullrhi")) {
        $args += "-nullrhi"
    }

    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "Running tests for module: $ModuleName" -ForegroundColor Cyan
    Write-Host "Filter: $Filter" -ForegroundColor Cyan
    Write-Host "Editor: $editorCmd" -ForegroundColor DarkGray
    Write-Host "============================================" -ForegroundColor Cyan

    $projectName = [System.IO.Path]::GetFileNameWithoutExtension($ProjectFile)
    $logsDir = Join-Path (Split-Path $ProjectFile -Parent) "Saved\Logs"
    $editorName = [System.IO.Path]::GetFileNameWithoutExtension($editorCmd)
    $logFile = Join-Path $logsDir "$editorName.log"
    # Remove old log to avoid parsing stale data
    if (Test-Path $logFile) {
        Remove-Item $logFile -Force -ErrorAction SilentlyContinue
    }

    $proc = Start-Process -FilePath $editorCmd -ArgumentList $args `
        -PassThru -NoNewWindow

    $timeoutMs = $Config.editorTimeoutSeconds * 1000
    $completed = $proc.WaitForExit($timeoutMs)

    if (-not $completed) {
        Write-Warning "Editor process timed out after $($Config.editorTimeoutSeconds) seconds. Killing..."
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        return @{ ExitCode = -1; LogFile = $logFile; TimedOut = $true; ReportDir = $moduleReportDir }
    }

    $proc.Refresh()
    $exitCode = if ($null -eq $proc.ExitCode) { 0 } else { $proc.ExitCode }
    $resolvedLogFile = Resolve-AutomationLogFile -LogsDir $logsDir -PreferredLogFile $logFile -ProjectName $projectName
    return @{ ExitCode = $exitCode; LogFile = $resolvedLogFile; TimedOut = $false; ReportDir = $moduleReportDir }
}

function Reset-ReportDirectory {
    param([string]$ReportDir)

    if (Test-Path $ReportDir) {
        Remove-Item -LiteralPath $ReportDir -Recurse -Force -ErrorAction Stop
    }
    New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null

    $staleReportFile = Join-Path $ReportDir "index.json"
    if (Test-Path $staleReportFile) {
        throw "Failed to clear stale automation report: $staleReportFile"
    }
}

function Resolve-AutomationLogFile {
    param([string]$LogsDir, [string]$PreferredLogFile, [string]$ProjectName)

    if (Test-Path $PreferredLogFile) {
        return $PreferredLogFile
    }
    if (-not (Test-Path $LogsDir)) {
        return $PreferredLogFile
    }

    $patterns = @("$ProjectName*.log", "UnrealEditor*.log")
    foreach ($pattern in $patterns) {
        $candidate = Get-ChildItem -LiteralPath $LogsDir -Filter $pattern -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($candidate) {
            return $candidate.FullName
        }
    }
    return $PreferredLogFile
}

# ============================================
# 9. Parse Log for Results
# ============================================
function Parse-TestResults {
    param([string]$LogFile, [hashtable]$Patterns, [string]$ReportDir = "")

    if ($ReportDir) {
        $reportResults = Parse-ReportResults -ReportDir $ReportDir
        if ($reportResults.summary.total -gt 0) {
            return $reportResults
        }
    }

    if (-not (Test-Path $LogFile)) {
        Write-Warning "Log file not found: $LogFile"
        return @{ tests = @(); summary = @{ total = 0; passed = 0; failed = 0; duration_ms = 0 } }
    }

    $lines = Get-Content $LogFile
    $tests = @()
    $currentTest = $null

    foreach ($line in $lines) {
        # Passed test
        if ($line -match $Patterns.testPassed) {
            $tests += [PSCustomObject]@{
                name = $Matches[1].Trim()
                passed = $true
                duration = $Matches[2].Trim()
                error = $null
            }
        }
        # Failed test
        elseif ($line -match $Patterns.testFailed) {
            $currentTest = [PSCustomObject]@{
                name = $Matches[1].Trim()
                passed = $false
                duration = ""
                error = ""
            }
            $tests += $currentTest
        }
        # Error detail (follows failed test)
        elseif ($currentTest -and ($line -match $Patterns.testError)) {
            $currentTest.error = $Matches[1].Trim()
        }
    }

    $passed = @($tests | Where-Object { $_.passed -eq $true }).Count
    $failed = @($tests | Where-Object { $_.passed -eq $false }).Count

    return @{
        tests = $tests
        summary = @{
            total = $tests.Count
            passed = $passed
            failed = $failed
            duration_ms = 0  # UE log does not always include per-test ms in consistent format
        }
    }
}

function Parse-ReportResults {
    param([string]$ReportDir)

    if (-not $ReportDir -or -not (Test-Path $ReportDir)) {
        return @{ tests = @(); summary = @{ total = 0; passed = 0; failed = 0; duration_ms = 0 } }
    }

    $reportFile = Join-Path $ReportDir "index.json"
    if (-not (Test-Path $reportFile)) {
        return @{ tests = @(); summary = @{ total = 0; passed = 0; failed = 0; duration_ms = 0 } }
    }

    $report = Get-Content -LiteralPath $reportFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $tests = @()
    foreach ($test in @($report.tests)) {
        $state = if ($test.state) { [string]$test.state } else { "" }
        $passed = $state -match '^(Success|Passed|Pass)$'
        $failed = $state -match '^(Fail|Failed|Error)$'
        if (-not $passed -and -not $failed) {
            continue
        }

        $errorMessages = @()
        foreach ($entry in @($test.entries)) {
            if ($entry.event -and $entry.event.type -match '^(Error|Warning)$' -and $entry.event.message) {
                $errorMessages += [string]$entry.event.message
            }
        }

        $name = if ($test.fullTestPath) { [string]$test.fullTestPath } elseif ($test.testDisplayName) { [string]$test.testDisplayName } else { [string]$test.name }
        $duration = if ($test.duration) { [string]$test.duration } else { "" }
        $tests += [PSCustomObject]@{
            name = $name
            passed = $passed
            duration = $duration
            error = if ($errorMessages.Count -gt 0) { $errorMessages -join "`n" } else { $null }
        }
    }

    $passedCount = @($tests | Where-Object { $_.passed -eq $true }).Count
    $failedCount = @($tests | Where-Object { $_.passed -eq $false }).Count

    return @{
        tests = $tests
        summary = @{
            total = $tests.Count
            passed = $passedCount
            failed = $failedCount
            duration_ms = 0
        }
    }
}

# ============================================
# 10. Save Results JSON
# ============================================
function Save-Results {
    param([hashtable]$Results, [string]$ProjectDir)

    $outputDir = Join-Path $ProjectDir "Saved\Automation"
    if (-not (Test-Path $outputDir)) {
        New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
    }

    $outputPath = Join-Path $outputDir "autotest_results.json"
    $Results | ConvertTo-Json -Depth 10 | Set-Content $outputPath

    return $outputPath
}

# ============================================
# 11. Run All Tests for Given Modules
# ============================================
function Invoke-TestRun {
    param(
        [string]$ProjectFile,
        [string]$EnginePath,
        [array]$Modules,
        [hashtable]$Config,
        [string]$ProjectDir,
        [string]$Scope,
        [switch]$NoNullRHI
    )

    $allResults = @{
        modules = @()
        overall = @{ total = 0; passed = 0; failed = 0 }
    }

    foreach ($mod in $Modules) {
        $filter = Get-TestFilter -ModuleName $mod -Scope $Scope -ProjectDir $ProjectDir
        $runResult = Run-Tests -ProjectFile $ProjectFile -EnginePath $EnginePath `
            -ModuleName $mod -Filter $filter -Config $Config -NoNullRHI:$NoNullRHI

        $results = Parse-TestResults -LogFile $runResult.LogFile -Patterns $Config.logPatterns -ReportDir $runResult.ReportDir

        if ($results.summary.total -eq 0) {
            $results.tests += [PSCustomObject]@{
                name = "$mod (NO TESTS PARSED)"
                passed = $false
                duration = ""
                error = "No automation test results were parsed. Check scope, module registration, log file, and raw report directory."
            }
            $results.summary.total = $results.tests.Count
            $results.summary.passed = @($results.tests | Where-Object { $_.passed -eq $true }).Count
            $results.summary.failed = @($results.tests | Where-Object { $_.passed -eq $false }).Count
        }

        if ($runResult.TimedOut) {
            $results.tests += [PSCustomObject]@{
                name = "$mod (TIMEOUT)"
                passed = $false
                duration = ""
                error = "Editor process timed out after $($Config.editorTimeoutSeconds) seconds"
            }
            # Recompute summary to keep counts consistent with tests array
            $results.summary.total = $results.tests.Count
            $results.summary.passed = @($results.tests | Where-Object { $_.passed -eq $true }).Count
            $results.summary.failed = @($results.tests | Where-Object { $_.passed -eq $false }).Count
        }

        $moduleResult = @{
            name = $mod
            filter = $filter
            exitCode = $runResult.ExitCode
            timedOut = $runResult.TimedOut
            logFile = $runResult.LogFile
            rawReportDir = $runResult.ReportDir
            results = $results
        }
        $allResults.modules += $moduleResult

        $allResults.overall.total += $results.summary.total
        $allResults.overall.passed += $results.summary.passed
        $allResults.overall.failed += $results.summary.failed
    }

    return $allResults
}

# ============================================
# Main Flow
# ============================================
if ($script:IsDotSourced) {
    return
}

$projectFile = Find-ProjectFile -ExplicitPath $ProjectPath
$projectDir = Split-Path $projectFile -Parent

# Scan modules
$allModules = Get-TestModules -ProjectDir $projectDir -Pattern $config.testModulePattern
if ($allModules.Count -eq 0) {
    Write-Error "No test modules found matching: $($config.testModulePattern)"
    exit 1
}

$modules = Filter-Modules -Modules $allModules -Scope $Scope -ProjectDir $projectDir
if ($modules.Count -eq 0) {
    Write-Error "No modules match scope: $Scope"
    exit 1
}

Write-Host "Test modules to run: $($modules -join ', ')" -ForegroundColor Green

# Build and resolve engine
$enginePath = Invoke-Build -ProjectFile $projectFile -Configuration $Configuration

# Run tests per module
$allResults = Invoke-TestRun -ProjectFile $projectFile -EnginePath $enginePath `
    -Modules $modules -Config $config -ProjectDir $projectDir -Scope $Scope -NoNullRHI:$NoNullRHI

# Save combined results
$resultsPath = Save-Results -Results $allResults -ProjectDir $projectDir
Write-Host "Results saved to: $resultsPath" -ForegroundColor Green

# Generate report
$reportScript = Join-Path $scriptDir "report.ps1"
if (Test-Path $reportScript) {
    & powershell -File "$reportScript" -ResultsPath "$resultsPath" -ProjectDir "$projectDir"
}

# Return exit code based on failures
if ($allResults.overall.failed -gt 0) {
    exit 1
}
exit 0

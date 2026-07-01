#Requires -Version 5.1
param(
    [string]$ProjectPath = "",
    [string]$SourceFile = "",
    [string]$EngineRoot = "",
    [string]$Target = "",
    [ValidateSet("Win64")]
    [string]$Platform = "Win64",
    [ValidateSet("Development", "Debug", "Shipping", "Test")]
    [string]$Configuration = "Development"
)

$ErrorActionPreference = "Stop"

function New-StatusResult {
    param(
        [string]$Health,
        [string[]]$Caveats,
        [string[]]$NextActions
    )

    [ordered]@{
        project_root = $null
        uproject_path = $null
        project_name = $null
        engine_root = $null
        target = $null
        platform = $Platform
        configuration = $Configuration
        clangd_path = $null
        compile_commands_path = $null
        compile_commands_mtime = $null
        clangd_running = $false
        index_state = "unknown"
        health = $Health
        caveats = $Caveats
        next_actions = $NextActions
        generate_compile_commands_command = $null
    }
}

function Find-ProjectFile {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        if (-not (Test-Path -LiteralPath $ExplicitPath)) {
            throw "ProjectPath does not exist: $ExplicitPath"
        }

        $item = Get-Item -LiteralPath $ExplicitPath
        if ($item.PSIsContainer) {
            $files = @(Get-ChildItem -LiteralPath $item.FullName -Filter "*.uproject" -File)
        } else {
            if ($item.Extension -ne ".uproject") {
                throw "ProjectPath must be a .uproject file or directory containing one: $ExplicitPath"
            }
            return $item.FullName
        }
    } else {
        $files = @(Get-ChildItem -LiteralPath "." -Filter "*.uproject" -File)
    }

    if ($files.Count -eq 0) {
        throw "No .uproject file found"
    }

    if ($files.Count -gt 1) {
        $names = ($files | ForEach-Object { $_.FullName }) -join ", "
        throw "Multiple .uproject files found; pass -ProjectPath explicitly: $names"
    }

    return $files[0].FullName
}

function Resolve-EnginePath {
    param(
        [string]$ProjectFile,
        [string]$ExplicitEngineRoot
    )

    if ($ExplicitEngineRoot) {
        if (Test-Path -LiteralPath $ExplicitEngineRoot) {
            return (Resolve-Path -LiteralPath $ExplicitEngineRoot).Path
        }

        return $null
    }

    $content = Get-Content -LiteralPath $ProjectFile -Raw | ConvertFrom-Json
    $engineAssociation = $content.EngineAssociation
    if (-not $engineAssociation) {
        return $null
    }

    $candidate = $null
    if ($engineAssociation -match '^\d+\.\d+') {
        $regPath = "HKLM:\SOFTWARE\EpicGames\Unreal Engine\$engineAssociation"
        try {
            $candidate = (Get-ItemProperty -Path $regPath -ErrorAction Stop).InstalledDirectory
        } catch {
            $candidate = $null
        }
    } else {
        $regPath = "HKCU:\SOFTWARE\Epic Games\Unreal Engine\Builds\$engineAssociation"
        try {
            $candidate = (Get-ItemProperty -Path $regPath -ErrorAction Stop).Path
        } catch {
            $candidate = $null
        }
    }

    if ($candidate -and (Test-Path -LiteralPath $candidate)) {
        return (Resolve-Path -LiteralPath $candidate).Path
    }

    return $null
}

function Find-Clangd {
    $command = Get-Command clangd -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    return $null
}

function Test-ClangdRunning {
    $process = Get-Process -Name "clangd" -ErrorAction SilentlyContinue | Select-Object -First 1
    return [bool]$process
}

function Find-CompileCommands {
    param([string]$ProjectRoot)

    $projectDb = Join-Path $ProjectRoot "compile_commands.json"
    if (Test-Path -LiteralPath $projectDb) {
        return (Get-Item -LiteralPath $projectDb).FullName
    }

    return $null
}

function Get-GeneratedHeaderCaveats {
    param([string]$FilePath)

    $caveats = New-Object System.Collections.Generic.List[string]
    if (-not $FilePath) {
        return @($caveats)
    }

    if (-not (Test-Path -LiteralPath $FilePath)) {
        $caveats.Add("SourceFile does not exist: $FilePath")
        return @($caveats)
    }

    $content = Get-Content -LiteralPath $FilePath -Raw
    if ($content -match '\.generated\.h') {
        $generatedIncludes = [regex]::Matches($content, '#include\s+"([^"]+\.generated\.h)"')
        foreach ($include in $generatedIncludes) {
            $generatedName = $include.Groups[1].Value
            $generatedPath = Join-Path (Split-Path -Parent $FilePath) $generatedName
            if (-not (Test-Path -LiteralPath $generatedPath)) {
                $caveats.Add("generated header is referenced but not found next to SourceFile: $generatedName")
            }
        }
    }

    if ($content -match 'GENERATED_BODY\s*\(') {
        $caveats.Add("GENERATED_BODY is present; UHT/reflection semantics require UBT/UHT confirmation")
    }

    return @($caveats)
}

function New-GenerateCompileCommandsCommand {
    param(
        [string]$EngineRoot,
        [string]$ProjectFile,
        [string]$BuildTarget
    )

    if (-not $EngineRoot) {
        return $null
    }

    $ubtExe = Join-Path $EngineRoot "Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.exe"
    if (Test-Path -LiteralPath $ubtExe) {
        return "`"$ubtExe`" -mode=GenerateClangDatabase -project=`"$ProjectFile`" -game -engine $BuildTarget $Configuration $Platform"
    }

    $ubtDll = Join-Path $EngineRoot "Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.dll"
    if (Test-Path -LiteralPath $ubtDll) {
        return "dotnet `"$ubtDll`" -mode=GenerateClangDatabase -project=`"$ProjectFile`" -game -engine $BuildTarget $Configuration $Platform"
    }

    $buildBat = Join-Path $EngineRoot "Engine\Build\BatchFiles\Build.bat"
    if (Test-Path -LiteralPath $buildBat) {
        return "`"$buildBat`" -mode=GenerateClangDatabase -project=`"$ProjectFile`" -game -engine $BuildTarget $Configuration $Platform"
    }

    return $null
}

$result = New-StatusResult -Health "invalid" -Caveats @() -NextActions @()

try {
    $projectFile = Find-ProjectFile -ExplicitPath $ProjectPath
    $projectRoot = Split-Path -Parent $projectFile
    $projectName = [System.IO.Path]::GetFileNameWithoutExtension($projectFile)
    if (-not $Target) {
        $Target = "${projectName}Editor"
    }

    $engineRoot = Resolve-EnginePath -ProjectFile $projectFile -ExplicitEngineRoot $EngineRoot
    $clangdPath = Find-Clangd
    $compileCommandsPath = Find-CompileCommands -ProjectRoot $projectRoot
    $caveats = New-Object System.Collections.Generic.List[string]
    $nextActions = New-Object System.Collections.Generic.List[string]

    if (-not $engineRoot) {
        $caveats.Add("EngineAssociation could not be resolved from registry")
        $nextActions.Add("provide_engine_root_or_register_engine")
    }

    if (-not $clangdPath) {
        $caveats.Add("clangd was not found on PATH")
        $nextActions.Add("install_or_add_clangd_to_path")
    }

    if (-not $compileCommandsPath) {
        $caveats.Add("compile_commands.json is missing from project root")
        $nextActions.Add("generate_compile_database")
    }

    foreach ($generatedCaveat in (Get-GeneratedHeaderCaveats -FilePath $SourceFile)) {
        $caveats.Add($generatedCaveat)
        $nextActions.Add("refresh_generated_headers")
    }

    $health = "ok"
    if (-not $compileCommandsPath) {
        $health = "broken"
    } elseif ((-not $engineRoot) -or (-not $clangdPath)) {
        $health = "degraded"
    }

    $mtime = $null
    if ($compileCommandsPath) {
        $mtime = (Get-Item -LiteralPath $compileCommandsPath).LastWriteTime.ToString("o")
    }

    $result.project_root = $projectRoot
    $result.uproject_path = $projectFile
    $result.project_name = $projectName
    $result.engine_root = $engineRoot
    $result.target = $Target
    $result.clangd_path = $clangdPath
    $result.compile_commands_path = $compileCommandsPath
    $result.compile_commands_mtime = $mtime
    $result.clangd_running = Test-ClangdRunning
    $result.health = $health
    $result.caveats = @($caveats)
    $result.next_actions = @($nextActions | Select-Object -Unique)
    $result.generate_compile_commands_command = New-GenerateCompileCommandsCommand -EngineRoot $engineRoot -ProjectFile $projectFile -BuildTarget $Target
} catch {
    $result.health = "invalid"
    $result.caveats = @($_.Exception.Message)
    $result.next_actions = @("provide_project_path")
}

$result | ConvertTo-Json -Depth 5

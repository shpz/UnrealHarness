"""UE5 engine path resolution and UBT/UAT invocation."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path
from typing import Optional


def _remove_readonly(func, path, exc_info):
    """shutil.rmtree onexc handler to remove read-only files on Windows."""
    if os.path.exists(path):
        os.chmod(path, stat.S_IWUSR)
        func(path)


def _extended_length_path(path: Path) -> str:
    resolved = str(path.resolve())
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved.lstrip("\\")
    return "\\\\?\\" + resolved


def safe_rmtree(path: Path, attempts: int = 3) -> None:
    """Remove a tree robustly on Windows workspaces with deep UE paths."""
    last_error: OSError | None = None
    for attempt in range(attempts):
        try:
            shutil.rmtree(_extended_length_path(path), onexc=_remove_readonly)
            return
        except OSError as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            time.sleep(0.5)
    if last_error is not None:
        raise last_error


class EnginePaths:
    def __init__(self, engine_root: Path):
        self.engine_root = engine_root.resolve()
        self.build_bat = self.engine_root / "Engine" / "Build" / "BatchFiles" / "Build.bat"
        self.editor_cmd = self.engine_root / "Engine" / "Binaries" / "Win64" / "UnrealEditor-Cmd.exe"

    def validate(self) -> None:
        if not self.build_bat.exists():
            raise RuntimeError(f"Build.bat not found: {self.build_bat}")
        if not self.editor_cmd.exists():
            raise RuntimeError(f"UnrealEditor-Cmd.exe not found: {self.editor_cmd}")


def read_uproject(project_path: Path) -> dict:
    uproject_path = project_path if project_path.suffix == ".uproject" else project_path / "TPSample.uproject"
    return json.loads(uproject_path.read_text(encoding="utf-8"))


def resolve_engine_root(engine_association: str) -> Path:
    import winreg

    # Launcher-installed: version number like 5.7
    if "." in engine_association and engine_association.replace(".", "").isdigit():
        for hive, key_fmt in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EpicGames\Unreal Engine\{}"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\EpicGames\Unreal Engine\{}"),
        ]:
            try:
                with winreg.OpenKey(hive, key_fmt.format(engine_association)) as key:
                    value, _ = winreg.QueryValueEx(key, "InstalledDirectory")
                    if value and Path(value).exists():
                        return Path(value)
            except OSError:
                continue

    # Source-built: GUID
    for hive, key_fmt in [
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Epic Games\Unreal Engine\Builds\{}"),
    ]:
        try:
            with winreg.OpenKey(hive, key_fmt.format(engine_association)) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
                if value and Path(value).exists():
                    return Path(value)
        except OSError:
            continue

    raise RuntimeError(
        f"Could not resolve Unreal EngineAssociation '{engine_association}' from registry."
    )


def get_engine_paths(project_path: Path, uproject_name: Optional[str] = None) -> EnginePaths:
    descriptor = read_uproject(project_path)
    engine_association = descriptor.get("EngineAssociation", "")
    if not engine_association:
        raise RuntimeError("Missing EngineAssociation in .uproject")
    root = resolve_engine_root(engine_association)
    paths = EnginePaths(root)
    paths.validate()
    return paths


def invoke_build(
    project_path: Path,
    target: str,
    platform: str = "Win64",
    configuration: str = "Development",
    uproject_name: Optional[str] = None,
    clean: bool = False,
    build_log_path: Optional[Path] = None,
) -> dict:
    """Invoke UBT Build.bat. If clean=True, deletes Intermediate/Binaries first."""
    project_path = project_path.resolve()
    uproject_file = project_path / uproject_name if uproject_name else project_path / "TPSample.uproject"
    if not uproject_file.exists():
        raise RuntimeError(f".uproject not found: {uproject_file}")

    paths = get_engine_paths(project_path, uproject_name)

    if clean:
        # Remove per-project generated directories to force a real build
        for d in ["Intermediate", "Binaries"]:
            p = project_path / d
            if p.exists():
                safe_rmtree(p)

    parent_log = build_log_path.parent if build_log_path else project_path / "Saved" / "Logs"
    parent_log.mkdir(parents=True, exist_ok=True)
    ubt_log = parent_log / "ubt.log"

    args = [
        str(paths.build_bat),
        target,
        platform,
        configuration,
        str(uproject_file),
        "-waitmutex",
        "-NoUBA",
        f"-log={ubt_log}",
    ]

    start = time.perf_counter()
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=str(project_path),
        shell=False,
    )
    elapsed = time.perf_counter() - start

    log_text = result.stdout + "\n" + result.stderr
    if build_log_path:
        build_log_path.parent.mkdir(parents=True, exist_ok=True)
        build_log_path.write_text(
            f"Command: {' '.join(args)}\n"
            f"WorkingDirectory: {project_path}\n"
            f"ExitCode: {result.returncode}\n"
            f"DurationSeconds: {elapsed:.3f}\n\n"
            f"{log_text}",
            encoding="utf-8",
        )

    return {
        "exit_code": result.returncode,
        "duration_seconds": round(elapsed, 3),
        "build_log_path": str(build_log_path) if build_log_path else None,
        "ubt_log_path": str(ubt_log),
        "engine_root": str(paths.engine_root),
        "command_line": " ".join(args),
    }


def invoke_automation(
    project_path: Path,
    test_filter: str,
    automation_dir: Path,
    uproject_name: Optional[str] = None,
) -> dict:
    """Invoke UnrealEditor-Cmd.exe for automation tests."""
    project_path = project_path.resolve()
    uproject_file = project_path / uproject_name if uproject_name else project_path / "TPSample.uproject"
    paths = get_engine_paths(project_path, uproject_name)

    automation_dir.mkdir(parents=True, exist_ok=True)
    automation_log = automation_dir / "automation.log"

    exec_cmds = f"Automation RunTests {test_filter}; Quit"
    args = [
        str(paths.editor_cmd),
        str(uproject_file),
        "-unattended",
        "-nopause",
        "-nosplash",
        "-nullrhi",
        "-NoSound",
        "-DDC-ForceMemoryCache",
        f"-ReportOutputPath={automation_dir}",
        f"-ExecCmds={exec_cmds}",
        "-TestExit=Automation Test Queue Empty",
        "-log",
        f"-abslog={automation_log}",
    ]

    start = time.perf_counter()
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=str(project_path),
        shell=False,
    )
    elapsed = time.perf_counter() - start

    stdout_path = automation_dir / "UnrealEditor-Cmd.stdout.log"
    stdout_path.write_text(result.stdout, encoding="utf-8")

    return {
        "exit_code": result.returncode,
        "duration_seconds": round(elapsed, 3),
        "automation_dir": str(automation_dir),
        "automation_log_path": str(automation_log),
        "stdout_path": str(stdout_path),
        "engine_root": str(paths.engine_root),
        "command_line": " ".join(args),
    }

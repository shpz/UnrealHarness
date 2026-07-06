"""Adapter abstract base class and built-in adapters."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import dataclasses


@dataclasses.dataclass
class AdapterResult:
    exit_code: int
    timed_out: bool
    duration_seconds: float
    adapter_wall_seconds: float
    failure_class: Optional[str] = None
    skills_usage: Optional[dict] = None


class Adapter(ABC):
    @abstractmethod
    def run(
        self,
        workspace_root: Path,
        instruction_path: Path,
        skills_root: Optional[Path],
        artifacts_dir: Path,
        timeout_minutes: int,
        task_dir: Optional[Path] = None,
        project_junction: Optional[Path] = None,
    ) -> AdapterResult:
        ...


class OracleAdapter(Adapter):
    def run(
        self,
        workspace_root: Path,
        instruction_path: Path,
        skills_root: Optional[Path],
        artifacts_dir: Path,
        timeout_minutes: int,
        task_dir: Optional[Path] = None,
        project_junction: Optional[Path] = None,
    ) -> AdapterResult:
        oracle_dir = task_dir or instruction_path.parent
        patch_file = oracle_dir / "oracle.patch"
        action_py = oracle_dir / "oracle.py"
        action_ps1 = oracle_dir / "oracle.ps1"
        project_path = workspace_root / "TPSample"
        adapter_sw = time.perf_counter()

        if patch_file.exists():
            result = subprocess.run(
                ["git", "apply", str(patch_file)],
                cwd=str(project_path),
                capture_output=True,
                text=True,
            )
        elif action_py.exists():
            result = subprocess.run(
                [os.sys.executable, str(action_py)],
                cwd=str(project_path),
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "WORKSPACE_ROOT": str(workspace_root),
                    "PROJECT_PATH": str(project_path),
                    "ARTIFACTS_PATH": str(artifacts_dir),
                },
                timeout=timeout_minutes * 60,
            )
        elif action_ps1.exists():
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(action_ps1)],
                cwd=str(project_path),
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "WORKSPACE_ROOT": str(workspace_root),
                    "PROJECT_PATH": str(project_path),
                    "ARTIFACTS_PATH": str(artifacts_dir),
                },
                timeout=timeout_minutes * 60,
            )
        else:
            return AdapterResult(
                exit_code=1,
                timed_out=False,
                duration_seconds=0.0,
                adapter_wall_seconds=0.0,
                failure_class="agent-crash",
            )

        elapsed = time.perf_counter() - adapter_sw
        return AdapterResult(
            exit_code=result.returncode,
            timed_out=False,
            duration_seconds=round(elapsed, 3),
            adapter_wall_seconds=round(elapsed, 3),
            failure_class="agent-crash" if result.returncode != 0 else None,
        )


class NoopAdapter(Adapter):
    def run(
        self,
        workspace_root: Path,
        instruction_path: Path,
        skills_root: Optional[Path],
        artifacts_dir: Path,
        timeout_minutes: int,
        task_dir: Optional[Path] = None,
        project_junction: Optional[Path] = None,
    ) -> AdapterResult:
        return AdapterResult(
            exit_code=0,
            timed_out=False,
            duration_seconds=0.0,
            adapter_wall_seconds=0.0,
        )


class ManualAdapter(Adapter):
    def run(
        self,
        workspace_root: Path,
        instruction_path: Path,
        skills_root: Optional[Path],
        artifacts_dir: Path,
        timeout_minutes: int,
        task_dir: Optional[Path] = None,
        project_junction: Optional[Path] = None,
    ) -> AdapterResult:
        print(f"\n[ManualAdapter] Workspace: {workspace_root}")
        print(f"[ManualAdapter] Instruction: {instruction_path}")
        print(f"[ManualAdapter] Skills: {skills_root}")
        print(f"[ManualAdapter] Please make changes in the workspace, then press Enter to continue...")
        input()
        return AdapterResult(
            exit_code=0,
            timed_out=False,
            duration_seconds=0.0,
            adapter_wall_seconds=0.0,
        )


class CodexAdapter(Adapter):
    def _find_codex_js(self) -> Path:
        candidates = [
            Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "@openai" / "codex" / "bin" / "codex.js",
            Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "@openai" / "codex" / "bin" / "codex.js",
        ]
        for p in candidates:
            if p.exists():
                return p
        node = shutil.which("node")
        if not node:
            raise RuntimeError("node not found in PATH")
        result = subprocess.run(
            ["npm", "root", "-g"],
            capture_output=True, text=True, check=True,
        )
        npm_root = Path(result.stdout.strip())
        p = npm_root / "@openai" / "codex" / "bin" / "codex.js"
        if p.exists():
            return p
        raise RuntimeError("Could not find codex.js. Is @openai/codex installed globally?")

    def run(
        self,
        workspace_root: Path,
        instruction_path: Path,
        skills_root: Optional[Path],
        artifacts_dir: Path,
        timeout_minutes: int,
        task_dir: Optional[Path] = None,
        project_junction: Optional[Path] = None,
    ) -> AdapterResult:
        codex_js = self._find_codex_js()
        project_path = project_junction if project_junction else workspace_root / "TPSample"

        prompt_parts = [instruction_path.read_text(encoding="utf-8")]
        if skills_root and skills_root.exists():
            prompt_parts.append("\n\n## Available Skills\n")
            for skill_dir in sorted(skills_root.iterdir()):
                if skill_dir.is_dir():
                    skill_md = skill_dir / "SKILL.md"
                    if skill_md.exists():
                        prompt_parts.append(f"\n### {skill_dir.name}\n")
                        prompt_parts.append(skill_md.read_text(encoding="utf-8"))
        prompt = "\n".join(prompt_parts)

        prompt_path = artifacts_dir / "agent.prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")

        stdout_path = artifacts_dir / "agent.stdout.log"
        stderr_path = artifacts_dir / "agent.stderr.log"
        last_message_path = artifacts_dir / "agent.last_message.json"

        cmd = [
            str(shutil.which("node") or "node"),
            str(codex_js),
            "exec",
            "--cd", str(project_path),
            "--dangerously-bypass-approvals-and-sandbox",
            "--json",
            "--output-last-message", str(last_message_path),
            "--ephemeral",
            "--skip-git-repo-check",
        ]

        adapter_sw = time.perf_counter()
        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_minutes * 60,
            )
            elapsed = time.perf_counter() - adapter_sw
            timed_out = False
        except subprocess.TimeoutExpired as e:
            elapsed = time.perf_counter() - adapter_sw
            stdout_text = e.stdout.decode("utf-8", errors="replace") if e.stdout else ""
            stderr_text = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
            stdout_path.write_text(stdout_text, encoding="utf-8")
            stderr_path.write_text(stderr_text, encoding="utf-8")
            return AdapterResult(
                exit_code=124,
                timed_out=True,
                duration_seconds=round(elapsed, 3),
                adapter_wall_seconds=round(elapsed, 3),
                failure_class="timeout",
            )

        stdout_path.write_text(result.stdout or "", encoding="utf-8")
        stderr_path.write_text(result.stderr or "", encoding="utf-8")

        failure_class = None
        if result.returncode != 0:
            failure_class = "agent-crash"

        return AdapterResult(
            exit_code=result.returncode,
            timed_out=False,
            duration_seconds=round(elapsed, 3),
            adapter_wall_seconds=round(elapsed, 3),
            failure_class=failure_class,
        )


def _project_uses_external_worktree(project_path: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--absolute-git-dir"],
        cwd=str(project_path),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    git_dir = Path(result.stdout.strip())
    try:
        git_dir.relative_to(project_path.resolve())
        return False
    except ValueError:
        return True


def _wait_for_lingering_ue_processes(project_path: Path, max_wait_seconds: float = 600.0) -> bool:
    project_str = str(project_path.resolve()).lower()
    start = time.perf_counter()
    while True:
        remaining = []
        try:
            output = subprocess.run(
                ["tasklist", "/FO", "CSV", "/V"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            return True

        for line in output.splitlines()[1:]:
            parts = [p.strip('"') for p in line.split("\",\"")]
            if len(parts) < 9:
                continue
            image_name = parts[0].lower()
            command_line = parts[8].lower()
            if image_name == "python.exe" and (project_str in command_line or "autotest.py" in command_line):
                remaining.append(parts[0])
                continue
            if image_name == "unrealeditor-cmd.exe" and project_str in command_line:
                remaining.append(parts[0])

        if not remaining:
            return True
        if time.perf_counter() - start > max_wait_seconds:
            # Kill remaining processes
            for name in remaining:
                subprocess.run(["taskkill", "/F", "/IM", name], capture_output=True)
            return False
        time.sleep(2.0)


class KimiCodeAdapter(Adapter):
    """Launch the Kimi Code CLI (kimi) to solve the task.

    Similar to CodexAdapter but uses the locally installed `kimi` command.
    """

    def _find_kimi(self) -> Path:
        """Find the kimi executable on Windows."""
        # 1. Try shutil.which (covers PATH)
        kimi = shutil.which("kimi")
        if kimi:
            return Path(kimi)

        # 2. Known user install location (most common on Windows)
        user_kimi = Path.home() / ".kimi-code" / "bin" / "kimi.exe"
        if user_kimi.exists():
            return user_kimi

        # 3. Try PowerShell (if available)
        try:
            ps_result = subprocess.run(
                ["powershell", "-Command", "Get-Command kimi -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source"],
                capture_output=True,
                text=True,
            )
            if ps_result.returncode == 0:
                path = ps_result.stdout.strip().strip('"\'')
                if path and Path(path).exists():
                    return Path(path)
        except FileNotFoundError:
            pass

        # 4. Fallback install locations
        candidates = [
            Path.home() / "AppData" / "Local" / "Programs" / "Kimi" / "kimi.exe",
            Path.home() / "AppData" / "Roaming" / "Kimi" / "kimi.exe",
            Path.home() / "AppData" / "Local" / "kimi" / "kimi.exe",
            Path("C:/Program Files/Kimi/kimi.exe"),
            Path("C:/Program Files (x86)/Kimi/kimi.exe"),
        ]
        for p in candidates:
            if p.exists():
                return p

        raise RuntimeError(
            "kimi CLI not found. Please install Kimi Code or add it to PATH."
        )

    def run(
        self,
        workspace_root: Path,
        instruction_path: Path,
        skills_root: Optional[Path],
        artifacts_dir: Path,
        timeout_minutes: int,
        task_dir: Optional[Path] = None,
        project_junction: Optional[Path] = None,
    ) -> AdapterResult:
        kimi = self._find_kimi()
        project_path = project_junction if project_junction else workspace_root / "TPSample"

        # Build prompt from instruction + skills context
        prompt_parts = [instruction_path.read_text(encoding="utf-8")]
        if skills_root and skills_root.exists():
            prompt_parts.append("\n\n## Available Skills\n")
            for skill_dir in sorted(skills_root.iterdir()):
                if skill_dir.is_dir():
                    skill_md = skill_dir / "SKILL.md"
                    if skill_md.exists():
                        prompt_parts.append(f"\n### {skill_dir.name}\n")
                        prompt_parts.append(skill_md.read_text(encoding="utf-8"))
        prompt = "\n".join(prompt_parts)

        prompt_parts.append("\n\n## Workspace Contract\n\n")
        prompt_parts.append(
            "- All compilation, test execution, and report generation must happen inside the current project directory.\n"
            "- Do not create additional git worktrees or copy the project to an external path to run Unreal Engine commands.\n"
            "- When invoking long-running scripts such as autotest.py, wait for the process to finish. Do not run them in the background.\n"
        )
        prompt = "\n".join(prompt_parts)

        # Write prompt to file for reference
        prompt_path = artifacts_dir / "agent.prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")

        stdout_path = artifacts_dir / "agent.stdout.log"
        stderr_path = artifacts_dir / "agent.stderr.log"

        # Build kimi command: -p (prompt mode) auto-approves actions
        cmd = [
            str(kimi),
            "--output-format", "text",
            "-p", prompt,
        ]
        if skills_root and skills_root.exists():
            cmd.extend(["--skills-dir", str(skills_root)])

        adapter_sw = time.perf_counter()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout_minutes * 60,
                cwd=str(project_path),
            )
            elapsed = time.perf_counter() - adapter_sw
            timed_out = False

            stdout_text = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
            stderr_text = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
            stdout_path.write_text(stdout_text, encoding="utf-8")
            stderr_path.write_text(stderr_text, encoding="utf-8")

        except subprocess.TimeoutExpired as e:
            elapsed = time.perf_counter() - adapter_sw
            stdout_text = e.stdout.decode("utf-8", errors="replace") if e.stdout else ""
            stderr_text = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
            stdout_path.write_text(stdout_text, encoding="utf-8")
            stderr_path.write_text(stderr_text, encoding="utf-8")
            return AdapterResult(
                exit_code=124,
                timed_out=True,
                duration_seconds=round(elapsed, 3),
                adapter_wall_seconds=round(elapsed, 3),
                failure_class="timeout",
            )

        failure_class = None
        if result.returncode != 0:
            failure_class = "agent-crash"

        if result.returncode == 0 and not timed_out:
            if _project_uses_external_worktree(project_path):
                failure_class = "agent-crash"
            elif not _wait_for_lingering_ue_processes(project_path):
                failure_class = "agent-crash"

        return AdapterResult(
            exit_code=result.returncode,
            timed_out=False,
            duration_seconds=round(elapsed, 3),
            adapter_wall_seconds=round(elapsed, 3),
            failure_class=failure_class,
        )

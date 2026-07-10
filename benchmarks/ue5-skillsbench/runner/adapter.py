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


def build_prompt(instruction_path: Path, skills_root: Optional[Path]) -> str:
    """Compose the agent prompt from the task instruction and injected skills.

    Each skill section carries its on-disk root path so agents can invoke
    bundled scripts (e.g. status.py) instead of only reading SKILL.md text.
    """
    prompt_parts = [instruction_path.read_text(encoding="utf-8")]
    if skills_root and skills_root.exists():
        prompt_parts.append("\n\n## Available Skills\n")
        for skill_dir in sorted(skills_root.iterdir()):
            if skill_dir.is_dir():
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists():
                    prompt_parts.append(f"\n### {skill_dir.name}\n")
                    prompt_parts.append(f"\nSkill root (scripts referenced below live here): `{skill_dir.resolve()}`\n")
                    prompt_parts.append(skill_md.read_text(encoding="utf-8"))
    return "\n".join(prompt_parts)


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
    ) -> AdapterResult:
        patch_file = (task_dir or instruction_path.parent) / "oracle.patch"
        if not patch_file.exists():
            return AdapterResult(
                exit_code=0,
                timed_out=False,
                duration_seconds=0.0,
                adapter_wall_seconds=0.0,
            )

        project_path = workspace_root / "TPSample"
        adapter_sw = time.perf_counter()
        result = subprocess.run(
            ["git", "apply", str(patch_file)],
            cwd=str(project_path),
            capture_output=True,
            text=True,
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
    def __init__(self, model: Optional[str] = None):
        self.model = model

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
    ) -> AdapterResult:
        codex_js = self._find_codex_js()
        project_path = workspace_root / "TPSample"

        prompt = build_prompt(instruction_path, skills_root)

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
        if self.model:
            cmd.extend(["-m", self.model])

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
    ) -> AdapterResult:
        kimi = self._find_kimi()
        project_path = workspace_root / "TPSample"

        prompt = build_prompt(instruction_path, skills_root)

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

        return AdapterResult(
            exit_code=result.returncode,
            timed_out=False,
            duration_seconds=round(elapsed, 3),
            adapter_wall_seconds=round(elapsed, 3),
            failure_class=failure_class,
        )

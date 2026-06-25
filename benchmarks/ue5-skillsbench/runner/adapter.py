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
            # No oracle patch expected for this task (e.g. smoke test)
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
    def _find_codex_js(self) -> Path:
        # Try common npm global paths
        candidates = [
            Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "@openai" / "codex" / "bin" / "codex.js",
            Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "@openai" / "codex" / "bin" / "codex.js",
        ]
        for p in candidates:
            if p.exists():
                return p
        # Try PATH
        node = shutil.which("node")
        if not node:
            raise RuntimeError("node not found in PATH")
        # Try npm root -g
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

        # Write prompt to file for reference
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
            "--skip-git-repo-check",  # workspace is git repo but just in case
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

        # Determine if codex exited with error or the build failed
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

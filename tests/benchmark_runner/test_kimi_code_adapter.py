from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from benchmarks.ue5_skillsbench.runner.adapter import KimiCodeAdapter, _wait_for_lingering_ue_processes


def _fake_run_for_kimi(real_run):
    """Run git commands for real; fake all other subprocess calls as success."""
    def inner(cmd, *args, **kwargs):
        if isinstance(cmd, list) and len(cmd) > 0 and cmd[0] == "git":
            return real_run(cmd, *args, **kwargs)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")
    return inner


def _fake_run_for_prompt(cmd, *args, **kwargs):
    """Simulate successful kimi run and a normal git worktree."""
    if isinstance(cmd, list) and len(cmd) > 0 and cmd[0] == "git":
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")


class KimiCodeAdapterPromptTests(unittest.TestCase):
    def test_prompt_contains_workspace_contract(self) -> None:
        adapter = KimiCodeAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp)
            workspace_root.mkdir(exist_ok=True)
            project_path = workspace_root / "TPSample"
            project_path.mkdir()
            artifacts_dir = workspace_root / "artifacts"
            artifacts_dir.mkdir()
            instruction_path = workspace_root / "instruction.md"
            instruction_path.write_text("Run tests.", encoding="utf-8")

            # _find_kimi requires the executable to exist; mock it
            adapter._find_kimi = lambda: Path("/fake/kimi.exe")  # type: ignore[method-assign]

            # Avoid actually launching the (fake) subprocess; we only inspect the prompt file
            with patch.object(subprocess, "run", side_effect=_fake_run_for_prompt):
                adapter.run(
                    workspace_root=workspace_root,
                    instruction_path=instruction_path,
                    skills_root=None,
                    artifacts_dir=artifacts_dir,
                    timeout_minutes=1,
                )

            prompt = (artifacts_dir / "agent.prompt.md").read_text(encoding="utf-8")
            self.assertIn("Workspace Contract", prompt)
            self.assertIn("current project directory", prompt)
            self.assertIn("Do not create additional git worktrees", prompt)
            self.assertIn("wait for the process to finish", prompt)



class KimiCodeAdapterPostRunTests(unittest.TestCase):
    def test_detects_external_git_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp)
            workspace_root.mkdir(exist_ok=True)
            project_path = workspace_root / "TPSample"
            project_path.mkdir()
            external_git = workspace_root / "external_git"
            external_git.mkdir()
            subprocess.run(["git", "init"], cwd=external_git, check=True, capture_output=True)
            artifacts_dir = workspace_root / "artifacts"
            artifacts_dir.mkdir()
            instruction_path = workspace_root / "instruction.md"
            instruction_path.write_text("Run tests.", encoding="utf-8")

            # Initialize a git repo with an external worktree pointer
            subprocess.run(["git", "init"], cwd=project_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "test"], cwd=project_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=project_path, check=True, capture_output=True)
            git_dir = project_path / ".git"
            shutil.rmtree(git_dir)
            git_file = project_path / ".git"
            git_file.write_text(
                f"gitdir: {str((external_git / '.git').resolve()).replace(chr(92), '/')}\n",
                encoding="utf-8",
            )

            adapter = KimiCodeAdapter()
            adapter._find_kimi = lambda: Path("/fake/kimi.exe")  # type: ignore[method-assign]

            with patch.object(subprocess, "run", side_effect=_fake_run_for_kimi(subprocess.run)):
                result = adapter.run(
                    workspace_root=workspace_root,
                    instruction_path=instruction_path,
                    skills_root=None,
                    artifacts_dir=artifacts_dir,
                    timeout_minutes=1,
                )

            self.assertEqual(result.failure_class, "agent-crash")

    def test_no_external_worktree_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp)
            workspace_root.mkdir(exist_ok=True)
            project_path = workspace_root / "TPSample"
            project_path.mkdir()
            artifacts_dir = workspace_root / "artifacts"
            artifacts_dir.mkdir()
            instruction_path = workspace_root / "instruction.md"
            instruction_path.write_text("Run tests.", encoding="utf-8")

            subprocess.run(["git", "init"], cwd=project_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "test"], cwd=project_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=project_path, check=True, capture_output=True)

            adapter = KimiCodeAdapter()
            adapter._find_kimi = lambda: Path("/fake/kimi.exe")  # type: ignore[method-assign]

            with patch.object(subprocess, "run", side_effect=_fake_run_for_kimi(subprocess.run)):
                result = adapter.run(
                    workspace_root=workspace_root,
                    instruction_path=instruction_path,
                    skills_root=None,
                    artifacts_dir=artifacts_dir,
                    timeout_minutes=1,
                )

            self.assertNotEqual(result.failure_class, "agent-crash")


class WaitForLingeringUeProcessesTests(unittest.TestCase):
    def test_kills_matched_python_pid_on_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp)
            project_path.mkdir(exist_ok=True)
            fake_output = (
                "Node,Name,CommandLine,ProcessId\r\n"
                f"DESKTOP,python.exe,\"python.exe {project_path / 'autotest.py'} arg\",12345\r\n"
            )

            def fake_run(cmd, *args, **kwargs):
                if cmd[:3] == ["wmic", "process", "where"]:
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=fake_output, stderr="")
                if cmd[:3] == ["taskkill", "/F", "/PID"]:
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

            with patch.object(subprocess, "run", side_effect=fake_run) as mock_run:
                with patch.object(time, "sleep"):
                    result = _wait_for_lingering_ue_processes(project_path, max_wait_seconds=-1.0)

            self.assertFalse(result)
            taskkill_calls = [
                call for call in mock_run.call_args_list
                if len(call.args[0]) >= 4 and call.args[0][:3] == ["taskkill", "/F", "/PID"]
            ]
            self.assertEqual(len(taskkill_calls), 1)
            self.assertEqual(taskkill_calls[0].args[0][3], "12345")

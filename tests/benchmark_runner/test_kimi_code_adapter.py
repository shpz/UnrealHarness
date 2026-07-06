from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.ue5_skillsbench.runner.adapter import KimiCodeAdapter


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
            with patch.object(subprocess, "run", return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")):
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

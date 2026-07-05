from __future__ import annotations

import importlib
from pathlib import Path
import tempfile
import textwrap
import unittest


adapter_module = importlib.import_module("benchmarks.ue5-skillsbench.runner.adapter")


class OracleAdapterTests(unittest.TestCase):
    def test_missing_oracle_file_fails_instead_of_nooping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            project = workspace / "TPSample"
            project.mkdir(parents=True)
            task_dir = root / "task"
            task_dir.mkdir()
            instruction = workspace / "instruction.md"
            instruction.write_text("task", encoding="utf-8")
            artifacts = root / "artifacts"
            artifacts.mkdir()

            result = adapter_module.OracleAdapter().run(
                workspace_root=workspace,
                instruction_path=instruction,
                skills_root=None,
                artifacts_dir=artifacts,
                timeout_minutes=1,
                task_dir=task_dir,
            )

        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(result.failure_class, "agent-crash")

    def test_oracle_action_script_executes_in_project_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            project = workspace / "TPSample"
            project.mkdir(parents=True)
            task_dir = root / "task"
            task_dir.mkdir()
            (task_dir / "oracle.py").write_text(
                textwrap.dedent(
                    """
                    from pathlib import Path

                    Path("oracle.marker").write_text("ok", encoding="utf-8")
                    """
                ).strip(),
                encoding="utf-8",
            )
            instruction = workspace / "instruction.md"
            instruction.write_text("task", encoding="utf-8")
            artifacts = root / "artifacts"
            artifacts.mkdir()

            result = adapter_module.OracleAdapter().run(
                workspace_root=workspace,
                instruction_path=instruction,
                skills_root=None,
                artifacts_dir=artifacts,
                timeout_minutes=1,
                task_dir=task_dir,
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual((project / "oracle.marker").read_text(encoding="utf-8"), "ok")


if __name__ == "__main__":
    unittest.main()

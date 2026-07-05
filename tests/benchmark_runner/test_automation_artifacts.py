from __future__ import annotations

import importlib
import json
from pathlib import Path
import tempfile
import unittest


automation_artifacts = importlib.import_module("benchmarks.ue5-skillsbench.runner.automation_artifacts")


class AutomationArtifactTests(unittest.TestCase):
    def test_collect_automation_artifacts_copies_known_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            artifacts = root / "artifacts"
            native_dir = project / "Saved" / "Automation" / "Reports" / "Raw" / "TPSample_Input"
            native_dir.mkdir(parents=True)
            (native_dir / "index.json").write_text(json.dumps({"tests": []}), encoding="utf-8")

            automation_dir = project / "Saved" / "Automation"
            (automation_dir / "autotest_results.json").write_text("{}", encoding="utf-8")
            report_md = automation_dir / "Reports" / "2026-07-05-autotest-report.md"
            report_md.write_text("# report", encoding="utf-8")
            (native_dir / "automation.log").write_text("log", encoding="utf-8")

            copied = automation_artifacts.collect_automation_artifacts(project, artifacts)

            self.assertEqual(
                sorted(path.relative_to(artifacts).as_posix() for path in copied),
                [
                    "automation/autotest_results.json",
                    "automation/editor.log",
                    "automation/index.json",
                    "automation/report.md",
                ],
            )
            self.assertTrue((artifacts / "automation" / "index.json").exists())
            self.assertTrue((artifacts / "automation" / "report.md").exists())


if __name__ == "__main__":
    unittest.main()

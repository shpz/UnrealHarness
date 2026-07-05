from __future__ import annotations

import importlib
from pathlib import Path
from unittest import mock
import unittest


unreal = importlib.import_module("benchmarks.ue5-skillsbench.runner.unreal")


class UnrealCleanTests(unittest.TestCase):
    def test_safe_rmtree_uses_extended_length_path_on_windows(self) -> None:
        with mock.patch.object(unreal.os, "name", "nt"), mock.patch.object(unreal.shutil, "rmtree") as rmtree:
            unreal.safe_rmtree(Path("D:/Workspace/Project/Intermediate"))

        delete_path = rmtree.call_args.args[0]
        self.assertTrue(str(delete_path).startswith("\\\\?\\"))
        self.assertIn("D:\\Workspace\\Project\\Intermediate", str(delete_path))


if __name__ == "__main__":
    unittest.main()

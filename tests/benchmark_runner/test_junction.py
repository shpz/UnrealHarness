from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from benchmarks.ue5_skillsbench.runner.junction import create_junction, is_junction, remove_junction, resolve_junction_root


class JunctionTests(unittest.TestCase):
    def test_resolve_junction_root_returns_writable_path(self) -> None:
        root = resolve_junction_root()
        self.assertTrue(root.exists())
        test_file = root / ".write_test"
        test_file.write_text("ok", encoding="utf-8")
        self.assertEqual(test_file.read_text(encoding="utf-8"), "ok")
        test_file.unlink()

    def test_create_and_remove_junction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.mkdir()
            (target / "file.txt").write_text("hello", encoding="utf-8")
            junction = Path(tmp) / "junction"
            create_junction(junction, target)
            self.assertTrue(is_junction(junction))
            self.assertEqual((junction / "file.txt").read_text(encoding="utf-8"), "hello")
            remove_junction(junction)
            self.assertFalse(junction.exists())


if __name__ == "__main__":
    unittest.main()

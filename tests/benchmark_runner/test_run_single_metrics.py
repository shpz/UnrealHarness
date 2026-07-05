from __future__ import annotations

import importlib
import unittest


runner_main = importlib.import_module("benchmarks.ue5-skillsbench.runner.__main__")


class RunSingleMetricsTests(unittest.TestCase):
    def test_duration_seconds_or_zero_treats_none_as_zero(self) -> None:
        self.assertEqual(runner_main.duration_seconds_or_zero({"duration_seconds": None}), 0.0)
        self.assertEqual(runner_main.duration_seconds_or_zero(None), 0.0)
        self.assertEqual(runner_main.duration_seconds_or_zero({"duration_seconds": 1.25}), 1.25)


if __name__ == "__main__":
    unittest.main()

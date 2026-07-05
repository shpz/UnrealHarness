from __future__ import annotations

import importlib
import sys


def _register_benchmark_alias() -> None:
    hyphen_name = "benchmarks.ue5-skillsbench"
    underscore_name = "benchmarks.ue5_skillsbench"
    if underscore_name in sys.modules:
        return
    try:
        hyphen_pkg = importlib.import_module(hyphen_name)
    except Exception:
        return
    sys.modules[underscore_name] = hyphen_pkg


_register_benchmark_alias()

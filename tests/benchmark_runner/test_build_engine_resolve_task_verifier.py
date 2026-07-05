from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


VERIFIER = Path("benchmarks/ue5-skillsbench/tasks/tps-build-engine-resolve/verifier.py")


class BuildEngineResolveTaskVerifierTests(unittest.TestCase):
    def test_unresolved_engine_association_is_reported_as_build_failure(self) -> None:
        verifier = _load_module("build_engine_resolve_verifier", VERIFIER)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            artifacts = root / "artifacts"
            project.mkdir()
            artifacts.mkdir()

            with mock.patch.dict(
                os.environ,
                {
                    "PROJECT_PATH": str(project),
                    "ARTIFACTS_PATH": str(artifacts),
                },
            ):
                with mock.patch.object(
                    verifier,
                    "invoke_build",
                    side_effect=RuntimeError(
                        "Could not resolve Unreal EngineAssociation "
                        "'00000000-0000-0000-0000-000000000000' from registry."
                    ),
                ):
                    with self.assertRaises(SystemExit) as exit_context:
                        verifier.main()

            self.assertEqual(exit_context.exception.code, 1)
            verifier_result = json.loads((artifacts / "verifier_result.json").read_text(encoding="utf-8"))
            self.assertFalse(verifier_result["passed"])
            self.assertEqual(verifier_result["failure_class"], "build")
            self.assertEqual(verifier_result["checks"][0]["name"], "engine_resolution")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path.resolve())
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()

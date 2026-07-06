from __future__ import annotations

import importlib
import unittest


runner_main = importlib.import_module("benchmarks.ue5-skillsbench.runner.__main__")
adapter_module = importlib.import_module("benchmarks.ue5-skillsbench.runner.adapter")
AdapterResult = adapter_module.AdapterResult


def make_adapter(
    *,
    exit_code: int = 0,
    timed_out: bool = False,
    failure_class: str | None = None,
) -> AdapterResult:
    return AdapterResult(
        exit_code=exit_code,
        timed_out=timed_out,
        duration_seconds=0.0,
        adapter_wall_seconds=0.0,
        failure_class=failure_class,
    )


def make_verifier(*, passed: bool, failure_class: str | None = None) -> dict:
    return {"verifier_result": {"passed": passed, "failure_class": failure_class}}


class TrialResultAggregationTests(unittest.TestCase):
    def test_adapter_failure_class_with_zero_exit_code_fails_trial(self) -> None:
        adapter = make_adapter(failure_class="agent-crash")
        verifier = make_verifier(passed=True)

        overall_passed, failure_class = runner_main._aggregate_trial_result(adapter, verifier)

        self.assertFalse(overall_passed)
        self.assertEqual(failure_class, "agent-crash")

    def test_nonzero_exit_code_without_failure_class_is_agent_crash(self) -> None:
        adapter = make_adapter(exit_code=1)
        verifier = make_verifier(passed=True)

        overall_passed, failure_class = runner_main._aggregate_trial_result(adapter, verifier)

        self.assertFalse(overall_passed)
        self.assertEqual(failure_class, "agent-crash")

    def test_timeout_failure_class_is_preserved(self) -> None:
        adapter = make_adapter(timed_out=True, failure_class="timeout")
        verifier = make_verifier(passed=True)

        overall_passed, failure_class = runner_main._aggregate_trial_result(adapter, verifier)

        self.assertFalse(overall_passed)
        self.assertEqual(failure_class, "timeout")

    def test_verifier_failure_is_reported_when_adapter_succeeds(self) -> None:
        adapter = make_adapter()
        verifier = make_verifier(passed=False, failure_class="build-fail")

        overall_passed, failure_class = runner_main._aggregate_trial_result(adapter, verifier)

        self.assertFalse(overall_passed)
        self.assertEqual(failure_class, "build-fail")

    def test_verifier_failure_without_failure_class_defaults_to_verifier_fail(self) -> None:
        adapter = make_adapter()
        verifier = {"verifier_result": {"passed": False}}

        overall_passed, failure_class = runner_main._aggregate_trial_result(adapter, verifier)

        self.assertFalse(overall_passed)
        self.assertEqual(failure_class, "verifier-fail")

    def test_successful_adapter_and_verifier_passes(self) -> None:
        adapter = make_adapter()
        verifier = make_verifier(passed=True)

        overall_passed, failure_class = runner_main._aggregate_trial_result(adapter, verifier)

        self.assertTrue(overall_passed)
        self.assertIsNone(failure_class)


if __name__ == "__main__":
    unittest.main()

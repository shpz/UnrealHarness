# Task

The project contains UE Automation tests for `TPSample.Error.Accumulator.*`, and one regression test is failing.

Run the relevant Automation scope, inspect the failure report, fix the root cause, and rerun the same scope until it passes.

Do not delete tests, skip tests, rename the scope, or weaken assertions. The expected repair is in the production error accumulator behavior, not in the test expectations.

## Required Artifacts

After running the Automation scope, leave at least one structured report so the verifier can parse the results:

- `Saved/Automation/Reports/Raw/<Scope>/index.json` (native Automation report), or
- `Saved/Automation/autotest_results.json` (structured JSON summary).

A markdown report or editor log alone is not sufficient. If you use `ue-autotest`, pass `-ReportExportPath="..."` to generate the native index.json and autotest_results.json.

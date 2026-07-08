# Run Scoped Automation Report

The project already contains multiple UE Automation test scopes.

Run only the input and error handling related tests. Do not run performance tests. Produce a pass/fail summary and include the report file path.

After running the tests, write a markdown summary report under `Saved/Automation/Reports/` that includes the selected scopes, total/passed/failed counts, and failure details (or "No failures").

## Required Artifacts

The markdown report alone is not sufficient. You must also leave at least one structured Automation report so the verifier can confirm the results:

- `Saved/Automation/Reports/Raw/<Scope>/index.json` (native Automation report), or
- `Saved/Automation/autotest_results.json` (structured JSON summary).

If you use `ue-autotest`, pass `-ReportExportPath="..."` to generate the native index.json and autotest_results.json; the skill also creates the markdown report automatically.

Keep the editor log produced by the test run (e.g. `Saved/Logs/UnrealEditor-Cmd.log`). The verifier cross-checks the structured report against the editor log to confirm the tests were actually executed.

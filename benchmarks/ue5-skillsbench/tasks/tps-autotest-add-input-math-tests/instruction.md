# Task

Add UE Automation tests for TPSample input math behavior.

The project now has a small input math helper in the main TPSample module. Create the required Editor test module and add at least three headless Automation tests under `TPSample.Input.Math.*`.

Create a new Editor test module named exactly `TPSampleTest` under `Source/TPSampleTest`. Do not place the tests in `TPSampleEditor` or any other module name.

Cover these cases:

- Normalizing move input outside the dead zone.
- Treating tiny move input as inside the dead zone.
- Quantizing look input to a stable step size.

Run the new test scope and leave the Automation results in the project so the run can be reviewed.

## Required Module Template

Create the Editor test module with exactly this structure:

- `Source/TPSampleTest/TPSampleTest.Build.cs`
- `.uproject` module entry: `Name=TPSampleTest`, `Type=Editor`
- `Source/TPSampleEditor.Target.cs`: add `ExtraModuleNames.Add("TPSampleTest")`
- `Source/TPSample.Target.cs`: do **not** add `TPSampleTest`
- `TPSampleTest.Build.cs` dependencies must include: `Core`, `CoreUObject`, `Engine`, `UnrealEd`, `TPSample`
- Test flags must be headless, e.g. `EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::EngineFilter` (macro form `EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags_EngineFilter` is also accepted)
- The test source file name is flexible as long as it is a `.cpp` under `Source/TPSampleTest/Private` and defines tests under `TPSample.Input.Math.*`.

## Required Artifacts

After running the tests, leave at least one structured report so the verifier can parse the results:

- `Saved/Automation/Reports/Raw/<Scope>/index.json` (native Automation report), or
- `Saved/Automation/autotest_results.json` (structured JSON summary).

A markdown report or editor log alone is not sufficient. If you use `ue-autotest`, pass `-ReportExportPath="..."` to generate the native index.json and autotest_results.json.

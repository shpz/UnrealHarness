# Task

Add UE Automation tests for TPSample input math behavior.

The project now has a small input math helper in the main TPSample module. Create the required Editor test module and add at least three headless Automation tests under `TPSample.Input.Math.*`.

Create a new Editor test module named exactly `TPSampleTest` under `Source/TPSampleTest`. Do not place the tests in `TPSampleEditor` or any other module name.

Cover these cases:

- Normalizing move input outside the dead zone.
- Treating tiny move input as inside the dead zone.
- Quantizing look input to a stable step size.

Run the new test scope and leave the Automation results in the project so the run can be reviewed.

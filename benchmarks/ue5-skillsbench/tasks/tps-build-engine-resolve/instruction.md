# Build Engine Resolve (GUID Registry)

The UE5 project's `.uproject` has been reconfigured to use a source-built engine association (GUID format). The GUID is correctly registered in the Windows registry under `HKCU\SOFTWARE\Epic Games\Unreal Engine\Builds\`.

Build the `TPSampleEditor` target for `Win64` `Development`.

The engine path must be resolved from the registry via the GUID-based `EngineAssociation`.

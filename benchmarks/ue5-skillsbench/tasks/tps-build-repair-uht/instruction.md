# Build Repair (UHT Reflection Error)

The UE5 project currently fails to build because a newly added header file uses a UPROPERTY type from a module that is not declared as a dependency. The error appears in UnrealHeaderTool-generated code, not in the original source file.

Repair the build failure so `TPSampleEditor` builds for `Win64` `Development`.

Do not delete the new header file, remove the UPROPERTY, or bypass the reflection logic.

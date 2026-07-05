"""Inject the TPSampleInputMath helper without adding Automation tests."""
from __future__ import annotations

from pathlib import Path


def main() -> None:
    project_path = Path.cwd()
    public_dir = project_path / "Source" / "TPSample" / "Public"
    private_dir = project_path / "Source" / "TPSample" / "Private"
    public_dir.mkdir(parents=True, exist_ok=True)
    private_dir.mkdir(parents=True, exist_ok=True)
    (public_dir / "TPSampleInputMath.h").write_text(_header(), encoding="utf-8")
    (private_dir / "TPSampleInputMath.cpp").write_text(_source(), encoding="utf-8")


def _header() -> str:
    return r"""#pragma once

#include "CoreMinimal.h"

namespace TPSampleInputMath
{
    TPSAMPLE_API FVector2D NormalizeMoveInput(const FVector2D& RawInput, float DeadZone);
    TPSAMPLE_API FVector2D QuantizeLookInput(const FVector2D& RawInput, float Step);
    TPSAMPLE_API bool IsInputWithinDeadZone(const FVector2D& RawInput, float DeadZone);
}
"""


def _source() -> str:
    return r"""#include "TPSampleInputMath.h"

namespace TPSampleInputMath
{
    FVector2D NormalizeMoveInput(const FVector2D& RawInput, float DeadZone)
    {
        const float ClampedDeadZone = FMath::Clamp(DeadZone, 0.0f, 1.0f);
        if (IsInputWithinDeadZone(RawInput, ClampedDeadZone))
        {
            return FVector2D::ZeroVector;
        }

        const float Size = RawInput.Size();
        if (Size <= KINDA_SMALL_NUMBER)
        {
            return FVector2D::ZeroVector;
        }

        return RawInput / Size;
    }

    FVector2D QuantizeLookInput(const FVector2D& RawInput, float Step)
    {
        if (Step <= KINDA_SMALL_NUMBER)
        {
            return RawInput;
        }

        return FVector2D(
            FMath::GridSnap(RawInput.X, Step),
            FMath::GridSnap(RawInput.Y, Step));
    }

    bool IsInputWithinDeadZone(const FVector2D& RawInput, float DeadZone)
    {
        return RawInput.Size() <= FMath::Max(0.0f, DeadZone);
    }
}
"""


if __name__ == "__main__":
    main()

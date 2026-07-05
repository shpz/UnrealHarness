"""Inject a source file that requires UMG, then remove the UMG dependency."""
from __future__ import annotations

from pathlib import Path


def main() -> None:
    project_path = Path.cwd()
    module_dir = project_path / "Source" / "TPSample"
    _write_widget(module_dir)
    _remove_umg_dependency(module_dir / "TPSample.Build.cs")


def _write_widget(module_dir: Path) -> None:
    (module_dir / "TPSampleDependencyWidget.h").write_text(
        r"""#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "TPSampleDependencyWidget.generated.h"

UCLASS()
class TPSAMPLE_API UTPSampleDependencyWidget : public UUserWidget
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintCallable, Category = "TPSample")
    FText GetDependencyLabel() const;
};
""",
        encoding="utf-8",
    )
    (module_dir / "TPSampleDependencyWidget.cpp").write_text(
        r"""#include "TPSampleDependencyWidget.h"

FText UTPSampleDependencyWidget::GetDependencyLabel() const
{
    return FText::FromString(TEXT("UMG dependency is configured"));
}
""",
        encoding="utf-8",
    )


def _remove_umg_dependency(build_cs: Path) -> None:
    text = build_cs.read_text(encoding="utf-8")
    text = text.replace('\n\t\t\t"UMG",', "")
    text = text.replace('\n            "UMG",', "")
    text = text.replace('\n            "UMG"', "")
    build_cs.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

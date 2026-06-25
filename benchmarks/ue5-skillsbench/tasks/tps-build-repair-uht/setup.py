"""Inject a UHT header that references a type from an undeclared module."""
import sys
from pathlib import Path


def main():
    project_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
    source_dir = project_path / "Source" / "TPSample"
    if not source_dir.exists():
        raise RuntimeError(f"Source directory not found: {source_dir}")

    fixture_path = source_dir / "SkillsBenchUHTProbe.h"
    fixture_source = '''#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"
#include "SkillsBenchUHTProbe.generated.h"

UCLASS()
class USkillsBenchUHTProbe : public UObject
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Tags")
	FGameplayTag TestTag;
};
'''
    fixture_path.write_text(fixture_source, encoding="utf-8")
    print(f"Injected UHT fixture: {fixture_path}")


if __name__ == "__main__":
    main()

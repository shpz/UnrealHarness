"""Setup: full build then modify source to simulate user coding."""
import sys
from pathlib import Path
import subprocess

# Allow importing runner modules
runner_path = Path(__file__).resolve().parents[2] / "runner"
sys.path.insert(0, str(runner_path))
from unreal import invoke_build


def main():
    project_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".").resolve()

    # 1. Full build first to ensure Binaries/Intermediate exist (cached state)
    print("Running initial full build (Development)...")
    result = invoke_build(
        project_path=project_path,
        target="TPSampleEditor",
        platform="Win64",
        configuration="Development",
        uproject_name="TPSample.uproject",
        clean=False,
    )
    print(
        f"Full build exit code: {result['exit_code']}, "
        f"duration: {result['duration_seconds']:.1f}s"
    )
    if result["exit_code"] != 0:
        raise RuntimeError("Initial full build failed")

    # 2. Modify existing code: change MaxWalkSpeed
    cpp_path = project_path / "Source" / "TPSample" / "TPSampleCharacter.cpp"
    h_path = project_path / "Source" / "TPSample" / "TPSampleCharacter.h"

    cpp_content = cpp_path.read_text(encoding="utf-8")
    h_content = h_path.read_text(encoding="utf-8")

    # --- Modify: change MaxWalkSpeed value ---
    cpp_content = cpp_content.replace(
        "GetCharacterMovement()->MaxWalkSpeed = 500.f;",
        "GetCharacterMovement()->MaxWalkSpeed = 600.f;",
    )
    print("Modified: MaxWalkSpeed 500.f -> 600.f")

    # --- Add: new DoSprint function in .cpp ---
    sprint_impl = """

void ATPSampleCharacter::DoSprint()
{
    // Increase max walk speed for sprinting
    GetCharacterMovement()->MaxWalkSpeed = 1000.f;
    UE_LOG(LogTemplateCharacter, Log, TEXT("Sprint started"));
}
"""
    cpp_content = cpp_content + sprint_impl
    print("Added: DoSprint() implementation")

    # --- Add: new DoSprint declaration in .h ---
    h_content = h_content.replace(
        "virtual void DoJumpEnd();",
        "virtual void DoJumpEnd();\n\n\t/** Handles sprint input */\n\tUFUNCTION(BlueprintCallable, Category=\"Input\")\n\tvirtual void DoSprint();",
    )
    print("Added: DoSprint() declaration in header")

    # --- Add: DEFINE_LOG_CATEGORY for the new log usage in DoSprint ---
    module_cpp = project_path / "Source" / "TPSample" / "TPSample.cpp"
    module_cpp_content = module_cpp.read_text(encoding="utf-8")
    module_cpp_content = module_cpp_content + "\nDEFINE_LOG_CATEGORY(LogTemplateCharacter)\n"
    module_cpp.write_text(module_cpp_content, encoding="utf-8")
    print("Added: DEFINE_LOG_CATEGORY(LogTemplateCharacter) in TPSample.cpp")

    # Write back
    cpp_path.write_text(cpp_content, encoding="utf-8")
    h_path.write_text(h_content, encoding="utf-8")

    # 3. Git commit the modifications so diff metrics capture changes
    subprocess.run(
        ["git", "add", "-A"],
        cwd=str(project_path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Simulate user code changes"],
        cwd=str(project_path),
        check=True,
        capture_output=True,
    )
    print("Changes committed to git")


if __name__ == "__main__":
    main()

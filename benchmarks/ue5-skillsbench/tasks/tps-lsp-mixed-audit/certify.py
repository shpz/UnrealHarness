"""Author-side certification for the tps-lsp-mixed-audit ground truth.

Proves via real UBT builds that:
1. correct fixtures (A, B, E) compile cleanly on top of the baseline project;
2. each faulty fixture (C, D) fails the build at the file/line/symbol declared
   in answer_key.json;
3. C and D do not mask each other when injected together;
then writes certification.json with SHA-256 fingerprints of every fixture.

Run from repo root:
    python benchmarks/ue5-skillsbench/tasks/tps-lsp-mixed-audit/certify.py

Requires the UE engine referenced by sample/TPSample to be installed.
Re-run whenever fixtures or the engine version change; setup.py refuses to
run against stale certification.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import NoReturn

TASK_DIR = Path(__file__).resolve().parent
BENCHMARK_ROOT = TASK_DIR.parents[1]
REPO_ROOT = TASK_DIR.parents[3]

sys.path.insert(0, str(BENCHMARK_ROOT / "runner"))
from unreal import invoke_build, read_uproject  # noqa: E402

FIXTURES_DIR = TASK_DIR / "fixtures" / "Bench"
ANSWER_KEY_PATH = TASK_DIR / "answer_key.json"
CERTIFICATION_PATH = TASK_DIR / "certification.json"
BASELINE_PROJECT = REPO_ROOT / "sample" / "TPSample"
COPY_EXCLUDES = {"Binaries", "DerivedDataCache", "Intermediate", "Saved", ".cache", ".git"}

# MSVC diagnostic format: <path>(<line>): or <path>(<line>,<col>): error C2xxx: <text>
MSVC_ERROR_RE = re.compile(r"^\s*(.+?)\((\d+)(?:,\d+)?\):\s+error\s+(C\d+):\s+(.*)$", re.MULTILINE)
LINE_TOLERANCE = 3


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_baseline(dest: Path) -> None:
    def ignore(directory: str, names: list[str]) -> set[str]:
        return {n for n in names if n in COPY_EXCLUDES}

    shutil.copytree(BASELINE_PROJECT, dest, ignore=ignore)


def inject(project: Path, module_relative_dir: str, stems: list[str]) -> None:
    target_dir = project / module_relative_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    for stem in stems:
        for suffix in (".h", ".cpp"):
            source = FIXTURES_DIR / f"{stem}{suffix}"
            shutil.copy2(source, target_dir / source.name)


def remove(project: Path, module_relative_dir: str, stems: list[str]) -> None:
    target_dir = project / module_relative_dir
    for stem in stems:
        for suffix in (".h", ".cpp"):
            candidate = target_dir / f"{stem}{suffix}"
            if candidate.exists():
                candidate.unlink()


def build(project: Path, log_path: Path, clean: bool) -> dict[str, object]:
    return invoke_build(
        project_path=project,
        target="TPSampleEditor",
        platform="Win64",
        configuration="Development",
        uproject_name="TPSample.uproject",
        clean=clean,
        build_log_path=log_path,
    )


def extract_errors(log_path: Path) -> list[dict[str, object]]:
    text = log_path.read_text(encoding="utf-8", errors="replace")
    errors: list[dict[str, object]] = []
    for match in MSVC_ERROR_RE.finditer(text):
        errors.append({
            "file": Path(match.group(1)).name,
            "line": int(match.group(2)),
            "code": match.group(3),
            "text": match.group(4),
        })
    return errors


def match_expected_error(errors: list[dict[str, object]], expected: dict[str, object]) -> dict[str, object] | None:
    expected_file = str(expected["error_file"]).lower()
    expected_line = int(str(expected["error_line"]))
    expected_symbol = str(expected["error_symbol"]).lower()
    for error in errors:
        if str(error["file"]).lower() != expected_file:
            continue
        if abs(int(str(error["line"])) - expected_line) > LINE_TOLERANCE:
            continue
        if expected_symbol not in str(error["text"]).lower():
            continue
        return error
    return None


def fail(step: str, detail: str) -> NoReturn:
    print(f"CERTIFICATION FAILED at {step}: {detail}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    answer_key = json.loads(ANSWER_KEY_PATH.read_text(encoding="utf-8"))
    module_dir = answer_key["module_relative_dir"]
    files = answer_key["files"]

    correct_stems = [s for s, spec in files.items() if not spec["has_code_errors"]]
    faulty = {s: spec for s, spec in files.items() if spec["has_code_errors"]}

    for stem in files:
        for suffix in (".h", ".cpp"):
            if not (FIXTURES_DIR / f"{stem}{suffix}").exists():
                fail("preflight", f"fixture missing: {stem}{suffix}")

    work_root = Path(tempfile.mkdtemp(prefix="lsp-audit-certify-"))
    project = work_root / "TPSample"
    logs_dir = work_root / "logs"
    logs_dir.mkdir()
    print(f"Certification workspace: {work_root}")

    step_results: dict[str, object] = {}
    succeeded = False
    try:
        copy_baseline(project)

        # Step 1: baseline + correct fixtures must compile.
        inject(project, module_dir, correct_stems)
        log = logs_dir / "step1_correct.log"
        started = time.perf_counter()
        result = build(project, log, clean=True)
        print(f"Step 1 (correct fixtures) exit={result['exit_code']} in {result['duration_seconds']}s")
        if result["exit_code"] != 0:
            fail("step1", f"correct fixtures {correct_stems} broke the build; see {log}")
        step_results["step1_correct_fixtures_build"] = {"exit_code": 0, "duration_seconds": result["duration_seconds"]}

        # Step 2: each faulty fixture alone must fail at the declared location.
        for stem, spec in faulty.items():
            inject(project, module_dir, [stem])
            log = logs_dir / f"step2_{stem}.log"
            result = build(project, log, clean=False)
            print(f"Step 2 ({stem}) exit={result['exit_code']} in {result['duration_seconds']}s")
            if result["exit_code"] == 0:
                fail("step2", f"{stem} was expected to fail the build but compiled; see {log}")
            errors = extract_errors(log)
            matched = match_expected_error(errors, spec)
            if matched is None:
                fail(
                    "step2",
                    f"{stem}: no build error matched file={spec['error_file']} "
                    f"line={spec['error_line']}±{LINE_TOLERANCE} symbol={spec['error_symbol']}; "
                    f"extracted: {errors[:5]}; see {log}",
                )
            print(f"  matched: {matched['file']}({matched['line']}): {matched['code']}: {str(matched['text'])[:100]}")
            step_results[f"step2_{stem}"] = {"matched_error": matched}
            remove(project, module_dir, [stem])

        # Step 3: both faulty fixtures together; neither error may be masked.
        inject(project, module_dir, list(faulty))
        log = logs_dir / "step3_both.log"
        result = build(project, log, clean=False)
        print(f"Step 3 (both faulty) exit={result['exit_code']} in {result['duration_seconds']}s")
        if result["exit_code"] == 0:
            fail("step3", f"faulty fixtures compiled together; see {log}")
        errors = extract_errors(log)
        for stem, spec in faulty.items():
            if match_expected_error(errors, spec) is None:
                fail("step3", f"{stem}'s error is masked when combined; extracted: {errors[:8]}; see {log}")
        step_results["step3_combined"] = {"errors_found": len(errors)}

        engine_association = read_uproject(project).get("EngineAssociation", "")

        certification = {
            "certified_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "engine_association": engine_association,
            "engine_root": result["engine_root"],
            "line_tolerance": LINE_TOLERANCE,
            "fixture_sha256": {
                f"{stem}{suffix}": sha256(FIXTURES_DIR / f"{stem}{suffix}")
                for stem in files
                for suffix in (".h", ".cpp")
            },
            "answer_key_sha256": sha256(ANSWER_KEY_PATH),
            "steps": step_results,
        }
        CERTIFICATION_PATH.write_text(json.dumps(certification, indent=4), encoding="utf-8")
        print(f"\nCERTIFIED. Wrote {CERTIFICATION_PATH}")
        succeeded = True
        return 0
    finally:
        if succeeded:
            shutil.rmtree(work_root, ignore_errors=True)
        else:
            print(f"Workspace kept for inspection: {work_root}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())

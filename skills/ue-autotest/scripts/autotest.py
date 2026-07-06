#!/usr/bin/env python3
"""
UE5 自动化测试运行器
=============================================
扫描测试模块，通过 ue-build 编译项目，使用 UnrealEditor-Cmd 运行自动化测试，
解析原生报告 / 日志，输出结构化结果并生成 Markdown 报告。

Usage:
    python autotest.py
    python autotest.py --scope CoreGameplayTest
    python autotest.py --scope "MyProject.AI.*"
    python autotest.py --scope unit
    python autotest.py --project "D:/Projects/MyGame/MyGame.uproject" --scope all
    python autotest.py -h

Exit codes:
    0   全部测试通过
    1   脚本错误或存在失败测试
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import winreg
from pathlib import Path
from typing import Any, NoReturn, Optional

# ── ANSI 颜色代码 ─────────────────────────────────────────────────────────────
_COLOR_CYAN    = "\033[36m"
_COLOR_GREEN   = "\033[32m"
_COLOR_YELLOW  = "\033[33m"
_COLOR_RED     = "\033[31m"
_COLOR_GRAY    = "\033[90m"
_COLOR_RESET   = "\033[0m"


def _color_print(msg: str, color: str = _COLOR_RESET) -> None:
    """如果终端支持，则使用 ANSI 颜色打印。"""
    if sys.stdout.isatty():
        print(f"{color}{msg}{_COLOR_RESET}")
    else:
        print(msg)


def _error_exit(msg: str, code: int = 1) -> NoReturn:
    """打印错误信息并以指定退出码终止。"""
    _color_print(msg, _COLOR_RED)
    sys.exit(code)


# ── 路径常量 ─────────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_ROOT = _SCRIPT_DIR.parent

# ── 硬编码默认配置（与 config.yaml 缺失字段时保持一致）──────────────────────
_DEFAULT_CONFIG: dict[str, Any] = {
    "testModulePattern": "Source/*Test/*.Build.cs",
    "editorTimeoutSeconds": 600,
    "editorExtraArgs": ["-unattended", "-nopause", "-nosplash", "-log"],
    "moduleCategories": {},
    "logPatterns": {
        "testPassed": r"LogAutomationController:\s+(.+?)\s+passed\s*\(([^)]+)\)",
        "testFailed": r"LogAutomationController:\s+(.+?)\s+failed",
        "testError": r"LogAutomationController:\s*Error:\s*(.+)",
    },
}


# ── 0. 配置加载 ───────────────────────────────────────────────────────────────
def _parse_scalar(value: str) -> Any:
    """将 YAML 标量字符串转换为 Python 值（int / str，去除引号）。"""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """极简 YAML 解析器：支持扁平标量、"- item" 字符串列表、一层嵌套映射。

    仅覆盖本 skill 的 config.yaml 结构，不引入第三方依赖。
    """
    result: dict[str, Any] = {}
    current_key: Optional[str] = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped == "---":
            continue

        indent = len(line) - len(line.lstrip())

        if indent == 0:
            # 顶层键
            key, _, rest = stripped.partition(":")
            key = key.strip()
            rest = rest.strip()
            if rest:
                result[key] = _parse_scalar(rest)
                current_key = None
            else:
                # 后续行决定其为列表或嵌套映射
                result[key] = None
                current_key = key
        elif current_key is not None:
            if stripped.startswith("- "):
                # 字符串列表项
                if not isinstance(result[current_key], list):
                    result[current_key] = []
                result[current_key].append(_parse_scalar(stripped[2:]))
            else:
                # 一层嵌套映射
                key, _, rest = stripped.partition(":")
                if not isinstance(result[current_key], dict):
                    result[current_key] = {}
                result[current_key][key.strip()] = _parse_scalar(rest)

    return result


def load_config(config_path: Path) -> dict[str, Any]:
    """加载 config.yaml 并与硬编码默认值合并（配置文件优先）。"""
    config: dict[str, Any] = {
        "testModulePattern": _DEFAULT_CONFIG["testModulePattern"],
        "editorTimeoutSeconds": _DEFAULT_CONFIG["editorTimeoutSeconds"],
        "editorExtraArgs": list(_DEFAULT_CONFIG["editorExtraArgs"]),
        "moduleCategories": dict(_DEFAULT_CONFIG["moduleCategories"]),
        "logPatterns": dict(_DEFAULT_CONFIG["logPatterns"]),
    }

    if not config_path.exists():
        _error_exit(f"配置文件未找到：{config_path}")

    text = config_path.read_text(encoding="utf-8")

    parsed: Optional[dict[str, Any]] = None
    try:
        import yaml  # type: ignore[import-untyped]

        parsed = yaml.safe_load(text)
    except ImportError:
        parsed = _parse_simple_yaml(text)

    if isinstance(parsed, dict):
        for key, value in parsed.items():
            if value is None:
                continue
            if key == "logPatterns" and isinstance(value, dict):
                config["logPatterns"].update(value)
            elif key == "moduleCategories" and isinstance(value, dict):
                config["moduleCategories"].update(value)
            else:
                config[key] = value

    return config


# ── 1. 项目发现 ───────────────────────────────────────────────────────────────
def find_project_file(explicit_path: str) -> Path:
    """从显式路径（.uproject 文件或目录）或当前工作目录自动检测项目文件。"""
    if explicit_path:
        p = Path(explicit_path).resolve()
        if not p.exists():
            _error_exit(f"项目路径不存在：{explicit_path}")

        if p.is_file():
            if p.suffix != ".uproject":
                _error_exit(f"--project 必须是项目目录或 .uproject 文件：{explicit_path}")
            return p

        uproject_files = sorted(p.glob("*.uproject"))
        if not uproject_files:
            _error_exit(f"目录中未找到 .uproject 文件：{p}")
        if len(uproject_files) > 1:
            _error_exit(f"目录中存在多个 .uproject 文件：{p}。请用 --project 指定具体文件。")
        return uproject_files[0].resolve()

    cwd = Path.cwd()
    uproject_files = sorted(cwd.glob("*.uproject"))
    if not uproject_files:
        _error_exit("当前目录未找到 .uproject 文件。请通过 --project 参数指定。")
    if len(uproject_files) > 1:
        _error_exit("当前目录存在多个 .uproject 文件。请通过 --project 参数指定。")
    return uproject_files[0].resolve()


# ── 2. 扫描测试模块 ───────────────────────────────────────────────────────────
def get_test_modules(project_dir: Path, pattern: str) -> list[str]:
    """按模式扫描测试模块（Source/*Test/*.Build.cs），返回模块名列表。"""
    modules: list[str] = []
    for build_cs in sorted(project_dir.glob(pattern)):
        module_name = re.sub(r"\.Build\.cs$", "", build_cs.name)
        modules.append(module_name)
    return modules


# ── 3. 按 Scope 过滤模块 ──────────────────────────────────────────────────────
def _scope_matches_prefix(scope: str, prefix: str) -> bool:
    """判断 scope 是否与自动化前缀互为前缀关系。"""
    normalized_scope = scope.rstrip("*").rstrip(".")
    normalized_prefix = prefix.rstrip("*").rstrip(".")

    if normalized_scope == normalized_prefix:
        return True
    if normalized_scope == normalized_prefix.split(".")[0]:
        return True
    if normalized_prefix.startswith(f"{normalized_scope}."):
        return True
    if normalized_scope.startswith(f"{normalized_prefix}."):
        return True
    return False


def filter_modules(
    modules: list[str],
    scopes: list[str],
    project_dir: Path,
    module_categories: dict[str, str],
) -> list[str]:
    """按 scope 列表过滤模块：all / 模块名 / 分类关键字 / 自动化前缀通配。"""
    known_categories = set(module_categories.values())
    if "all" in scopes or not scopes:
        return modules

    result: set[str] = set()
    for scope in scopes:
        if scope in modules:
            result.add(scope)
            continue
        if scope in known_categories:
            result.update(m for m in modules if module_categories.get(m) == scope)
            continue
        for mod in modules:
            prefix = re.sub(r"Test$", "", mod)
            automation_prefix = get_module_automation_prefix(project_dir, mod)
            if _scope_matches_prefix(scope, prefix) or _scope_matches_prefix(scope, automation_prefix):
                result.add(mod)

    return sorted(result)


# ── 4. 发现自动化测试前缀 ─────────────────────────────────────────────────────
def get_module_automation_prefix(project_dir: Path, module_name: str) -> str:
    """扫描模块源码中的 IMPLEMENT_SIMPLE_AUTOMATION_TEST，计算最长公共点分前缀。

    无法解析时回退为模块名去掉 'Test' 后缀。
    """
    fallback = re.sub(r"Test$", "", module_name)

    module_dir = project_dir / "Source" / module_name
    if not module_dir.exists():
        return fallback

    test_names: list[str] = []
    pattern = re.compile(
        r'IMPLEMENT_SIMPLE_AUTOMATION_TEST\s*\([\s\S]*?,\s*"([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)"',
        re.MULTILINE,
    )
    for source_file in module_dir.rglob("*"):
        if not source_file.is_file() or source_file.suffix not in (".cpp", ".h"):
            continue
        try:
            content = source_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in pattern.finditer(content):
            test_names.append(match.group(1))

    if not test_names:
        return fallback

    common_parts = test_names[0].split(".")
    for name in test_names[1:]:
        parts = name.split(".")
        max_len = min(len(common_parts), len(parts))
        index = 0
        while index < max_len and common_parts[index] == parts[index]:
            index += 1
        if index == 0:
            common_parts = []
            break
        common_parts = common_parts[:index]

    if not common_parts:
        return fallback
    return ".".join(common_parts)


# ── 5. 通过 ue-build 编译 ─────────────────────────────────────────────────────
def invoke_build(project_file: Path, configuration: str) -> None:
    """调用 ue-build/build.py 编译项目，失败则终止。"""
    build_script = (_SKILL_ROOT.parent / "ue-build" / "build.py").resolve()
    if not build_script.exists():
        _error_exit(f"ue-build 脚本未找到：{build_script}")

    _color_print("=" * 44, _COLOR_CYAN)
    _color_print("编译项目...", _COLOR_CYAN)
    _color_print("=" * 44, _COLOR_CYAN)

    cmd = [
        sys.executable,
        str(build_script),
        "--project", str(project_file),
        "--config", configuration,
    ]
    try:
        result = subprocess.run(cmd, check=False)
    except OSError as exc:
        _error_exit(f"执行 build.py 失败：{exc}")
        return  # 不可达

    if result.returncode != 0:
        _error_exit(f"编译失败，退出码：{result.returncode}。跳过测试运行。", result.returncode)


# ── 6. 从 Scope 推导测试过滤器 ────────────────────────────────────────────────
def convert_scope_to_automation_filter(scope: str) -> str:
    """将通配 scope 转换为 Automation RunTests 过滤器。"""
    return scope.rstrip("*").rstrip(".")


def reduce_filters(filters: list[str]) -> list[str]:
    """去重并归并被覆盖的过滤器。

    若过滤器 B 等于 A 或以 "A." 开头，则 B 已被 A 覆盖，剔除 B，
    避免同一批测试在单次运行中被重复匹配。
    """
    unique = sorted(set(f for f in filters if f), key=len)
    reduced: list[str] = []
    for candidate in unique:
        covered = any(
            candidate == kept or candidate.startswith(f"{kept}.")
            for kept in reduced
        )
        if not covered:
            reduced.append(candidate)
    return sorted(reduced)


def build_run_filters(
    modules: list[str],
    module_prefixes: dict[str, str],
    scopes: list[str],
) -> list[str]:
    """确定本次运行的过滤器集合。

    支持多个 scope：all 时汇总所有模块前缀；模块名时使用其自动化前缀；
    通配前缀则转换为对应过滤器，最终归并去重。
    """
    filters: list[str] = []
    for raw_scope in scopes:
        for scope in raw_scope.split("+"):
            scope = scope.strip()
            if not scope:
                continue
            if scope == "all":
                filters.extend(module_prefixes[mod] for mod in modules)
            elif scope in modules:
                filters.append(module_prefixes[scope])
            else:
                scope_filter = convert_scope_to_automation_filter(scope)
                if scope_filter:
                    filters.append(scope_filter)
    return reduce_filters(filters)


# ── 7. 引擎路径解析（复用 ue-build 逻辑）─────────────────────────────────────
def resolve_engine_path(project_file: Path) -> Path:
    """读取 .uproject 的 EngineAssociation 并通过 Windows 注册表定位引擎。"""
    try:
        with project_file.open("r", encoding="utf-8") as fh:
            uproject_data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        _error_exit(f"读取/解析 .uproject 文件失败：{exc}")

    engine_association = uproject_data.get("EngineAssociation")
    if not engine_association:
        _error_exit("未能从 .uproject 中读取 EngineAssociation 字段")

    engine_path_str: Optional[str] = None

    # 判断是版本号（如 "5.5"）还是 GUID
    if re.match(r"^\d+\.\d+$", engine_association):
        # Launcher 安装的引擎
        reg_path = rf"SOFTWARE\EpicGames\Unreal Engine\{engine_association}"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                engine_path_str, _ = winreg.QueryValueEx(key, "InstalledDirectory")
        except FileNotFoundError:
            _error_exit(
                f"未找到 UE {engine_association} 的注册表项。"
                "请通过 Epic Games Launcher 验证安装。"
            )
    else:
        # 源码编译的引擎（GUID 格式）
        reg_path = rf"SOFTWARE\Epic Games\Unreal Engine\Builds\{engine_association}"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
                engine_path_str, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            _error_exit(
                "未找到源码编译引擎的注册表项。"
                "请验证引擎是否正确注册。"
            )

    if not engine_path_str:
        _error_exit("注册表中的引擎路径为空。")

    engine_path = Path(engine_path_str)
    if not engine_path.exists():
        _error_exit(f"引擎路径不存在：{engine_path}")

    return engine_path


def resolve_editor_cmd(engine_path: Path) -> Path:
    """定位 UnrealEditor-Cmd.exe。"""
    editor_cmd = engine_path / "Engine" / "Binaries" / "Win64" / "UnrealEditor-Cmd.exe"
    if not editor_cmd.exists():
        _error_exit(f"UnrealEditor-Cmd.exe 未找到：{editor_cmd}")
    return editor_cmd


# ── 8. 运行单个模块的测试 ─────────────────────────────────────────────────────
def reset_report_directory(report_dir: Path) -> None:
    """清空并重建模块报告目录，防止解析到陈旧报告。"""
    if report_dir.exists():
        shutil.rmtree(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    stale_report_file = report_dir / "index.json"
    if stale_report_file.exists():
        _error_exit(f"清理陈旧自动化报告失败：{stale_report_file}")


def resolve_automation_log_file(
    logs_dir: Path, preferred_log_file: Path, project_name: str
) -> Path:
    """解析编辑器日志文件。

    优先 Saved/Logs/UnrealEditor-Cmd.log，其次按修改时间取最新的
    "<项目名>*.log"，再次 "UnrealEditor*.log"。
    """
    if preferred_log_file.exists():
        return preferred_log_file
    if not logs_dir.exists():
        return preferred_log_file

    for pattern in (f"{project_name}*.log", "UnrealEditor*.log"):
        candidates = [p for p in logs_dir.glob(pattern) if p.is_file()]
        if candidates:
            return max(candidates, key=lambda p: p.stat().st_mtime)
    return preferred_log_file


def run_tests(
    project_file: Path,
    engine_path: Path,
    run_label: str,
    filters: list[str],
    config: dict[str, Any],
    no_null_rhi: bool,
) -> dict[str, Any]:
    """启动 UnrealEditor-Cmd，单次运行所有过滤器对应的自动化测试。"""
    editor_cmd = resolve_editor_cmd(engine_path)

    project_dir = project_file.parent
    automation_dir = project_dir / "Saved" / "Automation"
    automation_dir.mkdir(parents=True, exist_ok=True)
    module_report_dir = automation_dir / "Reports" / "Raw" / run_label
    reset_report_directory(module_report_dir)

    # Automation RunTests 支持 "+" 连接多个过滤器，单次编辑器启动跑完全部
    exec_cmds = f"Automation RunTests {'+'.join(filters)}; Quit"
    # 注意：必须手工拼接命令行字符串。若以列表传给 Popen，list2cmdline 会把
    # -ExecCmds="..." 中的引号转义为 \"，导致 UE 解析原始命令行时读到错误的值。
    cmd_parts: list[str] = [
        f'"{editor_cmd}"',
        f'"{project_file}"',
        f'-ExecCmds="{exec_cmds}"',
        '-TestExit="Automation Test Queue Empty"',
        f'-ReportExportPath="{module_report_dir}"',
    ] + list(config["editorExtraArgs"])

    if not no_null_rhi and "-nullrhi" not in cmd_parts:
        cmd_parts.append("-nullrhi")

    _color_print("=" * 44, _COLOR_CYAN)
    _color_print(f"运行测试：{run_label}", _COLOR_CYAN)
    _color_print(f"过滤器：{' + '.join(filters)}", _COLOR_CYAN)
    _color_print(f"编辑器：{editor_cmd}", _COLOR_GRAY)
    _color_print("=" * 44, _COLOR_CYAN)

    project_name = project_file.stem
    logs_dir = project_dir / "Saved" / "Logs"
    log_file = logs_dir / f"{editor_cmd.stem}.log"
    # 删除旧日志，避免解析到陈旧数据
    if log_file.exists():
        try:
            log_file.unlink()
        except OSError:
            pass

    timeout_seconds = int(config["editorTimeoutSeconds"])
    timed_out = False
    exit_code = 0
    # 以原始字符串启动，绕过 list2cmdline 的引号转义
    proc = subprocess.Popen(" ".join(cmd_parts))
    try:
        exit_code = proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _color_print(
            f"警告：编辑器进程超时（{timeout_seconds} 秒），正在终止...",
            _COLOR_YELLOW,
        )
        proc.kill()
        proc.wait()
        timed_out = True
        exit_code = -1

    if timed_out:
        return {
            "exitCode": -1,
            "logFile": log_file,
            "timedOut": True,
            "reportDir": module_report_dir,
        }

    resolved_log_file = resolve_automation_log_file(logs_dir, log_file, project_name)
    return {
        "exitCode": exit_code if exit_code is not None else 0,
        "logFile": resolved_log_file,
        "timedOut": False,
        "reportDir": module_report_dir,
    }


# ── 9. 解析测试结果 ───────────────────────────────────────────────────────────
def _empty_results() -> dict[str, Any]:
    """构造空结果结构。"""
    return {
        "tests": [],
        "summary": {"total": 0, "passed": 0, "failed": 0, "duration_ms": 0},
    }


def parse_report_results(report_dir: Path) -> dict[str, Any]:
    """解析引擎导出的原生自动化报告 index.json（优先数据源）。"""
    if not report_dir or not report_dir.exists():
        return _empty_results()

    report_file = report_dir / "index.json"
    if not report_file.exists():
        return _empty_results()

    try:
        # 引擎导出的 index.json 可能带 UTF-8 BOM
        report = json.loads(report_file.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return _empty_results()

    tests: list[dict[str, Any]] = []
    for test in report.get("tests") or []:
        state = str(test.get("state") or "")
        passed = bool(re.match(r"^(Success|Passed|Pass)$", state))
        failed = bool(re.match(r"^(Fail|Failed|Error)$", state))
        if not passed and not failed:
            continue

        error_messages: list[str] = []
        for entry in test.get("entries") or []:
            event = entry.get("event") or {}
            if re.match(r"^(Error|Warning)$", str(event.get("type") or "")) and event.get("message"):
                error_messages.append(str(event["message"]))

        name = str(
            test.get("fullTestPath")
            or test.get("testDisplayName")
            or test.get("name")
            or ""
        )
        duration = str(test.get("duration") or "")
        tests.append({
            "name": name,
            "passed": passed,
            "duration": duration,
            "error": "\n".join(error_messages) if error_messages else None,
        })

    passed_count = sum(1 for t in tests if t["passed"])
    failed_count = sum(1 for t in tests if not t["passed"])

    return {
        "tests": tests,
        "summary": {
            "total": len(tests),
            "passed": passed_count,
            "failed": failed_count,
            "duration_ms": 0,
        },
    }


def parse_test_results(
    log_file: Path, patterns: dict[str, str], report_dir: Optional[Path] = None
) -> dict[str, Any]:
    """解析测试结果：优先原生报告 index.json，回退到日志正则解析。"""
    if report_dir:
        report_results = parse_report_results(report_dir)
        if report_results["summary"]["total"] > 0:
            return report_results

    if not log_file.exists():
        _color_print(f"警告：日志文件未找到：{log_file}", _COLOR_YELLOW)
        return _empty_results()

    passed_re = re.compile(patterns["testPassed"])
    failed_re = re.compile(patterns["testFailed"])
    error_re = re.compile(patterns["testError"])

    tests: list[dict[str, Any]] = []
    current_test: Optional[dict[str, Any]] = None

    for line in log_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        passed_match = passed_re.search(line)
        if passed_match:
            tests.append({
                "name": passed_match.group(1).strip(),
                "passed": True,
                "duration": passed_match.group(2).strip(),
                "error": None,
            })
            continue

        failed_match = failed_re.search(line)
        if failed_match:
            current_test = {
                "name": failed_match.group(1).strip(),
                "passed": False,
                "duration": "",
                "error": "",
            }
            tests.append(current_test)
            continue

        # 错误详情（紧随失败测试之后）
        if current_test is not None:
            error_match = error_re.search(line)
            if error_match:
                current_test["error"] = error_match.group(1).strip()

    passed = sum(1 for t in tests if t["passed"])
    failed = sum(1 for t in tests if not t["passed"])

    return {
        "tests": tests,
        "summary": {
            "total": len(tests),
            "passed": passed,
            "failed": failed,
            # UE 日志中的每测试耗时格式不稳定，此处不统计
            "duration_ms": 0,
        },
    }


# ── 10. 保存结果 JSON ─────────────────────────────────────────────────────────
def save_results(results: dict[str, Any], project_dir: Path) -> Path:
    """将合并结果写入 Saved/Automation/autotest_results.json。"""
    output_dir = project_dir / "Saved" / "Automation"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "autotest_results.json"
    output_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path


# ── 11. 单次运行所有模块的测试并按前缀归属结果 ────────────────────────────────
def _recompute_summary(results: dict[str, Any]) -> None:
    """根据 tests 数组重算 summary，保持计数一致。"""
    tests = results["tests"]
    results["summary"]["total"] = len(tests)
    results["summary"]["passed"] = sum(1 for t in tests if t["passed"])
    results["summary"]["failed"] = sum(1 for t in tests if not t["passed"])


def attribute_tests_to_modules(
    tests: list[dict[str, Any]],
    modules: list[str],
    module_prefixes: dict[str, str],
) -> dict[str, list[dict[str, Any]]]:
    """按自动化前缀把测试结果归属到各模块。

    取匹配前缀最长的模块（更具体者优先）；无归属的测试
    统一放入 "(unattributed)" 桶，保证不丢结果。
    """
    buckets: dict[str, list[dict[str, Any]]] = {mod: [] for mod in modules}
    for test in tests:
        name = str(test.get("name") or "")
        best_module: Optional[str] = None
        best_length = -1
        for mod in modules:
            prefix = module_prefixes[mod]
            if (name == prefix or name.startswith(f"{prefix}.")) and len(prefix) > best_length:
                best_module = mod
                best_length = len(prefix)
        if best_module is None:
            buckets.setdefault("(unattributed)", []).append(test)
        else:
            buckets[best_module].append(test)
    return buckets

def _build_module_results(
    buckets: dict[str, list[dict[str, Any]]],
    mod: str,
    module_prefixes: dict[str, str],
    filters: list[str],
    run_result: dict[str, Any],
) -> dict[str, Any]:
    results = {
        "tests": list(buckets.get(mod, [])),
        "summary": {"total": 0, "passed": 0, "failed": 0, "duration_ms": 0},
    }
    _recompute_summary(results)

    return {
        "name": mod,
        "filter": module_prefixes.get(mod, "+".join(filters)),
        "exitCode": run_result["exitCode"],
        "timedOut": run_result["timedOut"],
        "logFile": str(run_result["logFile"]),
        "rawReportDir": str(run_result["reportDir"]),
        "results": results,
    }


def invoke_test_run(
    project_file: Path,
    engine_path: Path,
    modules: list[str],
    config: dict[str, Any],
    project_dir: Path,
    scopes: list[str],
    no_null_rhi: bool,
) -> dict[str, Any]:
    """单次启动编辑器运行所有过滤器，并将结果按模块归属汇总。"""
    module_prefixes = {
        mod: get_module_automation_prefix(project_dir, mod) for mod in modules
    }
    filters = build_run_filters(modules, module_prefixes, scopes)
    if not filters:
        _error_exit("未能从模块或 scope 推导出任何测试过滤器。")

    run_label = "_".join(scopes) if scopes and scopes != ["all"] else "All"
    run_label = re.sub(r'[<>?:"/\\|?*+ ]', "_", run_label)
    run_result = run_tests(
        project_file, engine_path, run_label, filters, config, no_null_rhi
    )

    parsed = parse_test_results(
        run_result["logFile"], config["logPatterns"], run_result["reportDir"]
    )

    buckets = attribute_tests_to_modules(parsed["tests"], modules, module_prefixes)

    all_results: dict[str, Any] = {
        "modules": [],
        "overall": {"total": 0, "passed": 0, "failed": 0},
    }

    bucket_names = modules + (
        ["(unattributed)"] if "(unattributed)" in buckets else []
    )
    for mod in bucket_names:
        module_result = _build_module_results(
            buckets, mod, module_prefixes, filters, run_result
        )
        all_results["modules"].append(module_result)

        module_tests = module_result["results"]["tests"]
        all_results["overall"]["total"] += len(module_tests)
        all_results["overall"]["passed"] += sum(
            1 for t in module_tests if t.get("passed")
        )
        all_results["overall"]["failed"] += sum(
            1 for t in module_tests if not t.get("passed")
        )

    return all_results


# ── 主流程 ───────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(
        description="UE5 自动化测试运行器",
        epilog='示例：python autotest.py --scope "MyProject.AI.*"',
    )
    parser.add_argument(
        "--project", "-p",
        metavar="路径",
        default="",
        help=".uproject 文件或项目目录（可选，默认从当前目录自动检测）",
    )
    parser.add_argument(
        "--scope", "-s",
        metavar="范围",
        action="append",
        default=[],
        help=(
            '测试范围（默认：all）。可为 "all"、模块名、'
            '自动化前缀通配（如 "MyProject.AI.*"）或分类关键字（unit/integration/performance）。'
            '可多次指定以运行多个 scope，或用 "+" 连接多个 scope。'
        ),
    )
    parser.add_argument(
        "--config", "-c",
        choices=["Development", "Debug"],
        default="Development",
        help="编译配置（默认：Development）",
    )
    parser.add_argument(
        "--no-null-rhi",
        action="store_true",
        help="不向编辑器参数附加 -nullrhi",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="跳过编译步骤",
    )
    args = parser.parse_args()

    raw_scopes = args.scope if args.scope else ["all"]
    normalized_scopes: list[str] = []
    for scope in raw_scopes:
        for part in scope.split("+"):
            part = part.strip()
            if part:
                normalized_scopes.append(part)
    if not normalized_scopes:
        normalized_scopes = ["all"]

    # ── 加载配置 ──
    config = load_config(_SKILL_ROOT / "config.yaml")

    # ── 发现项目 ──
    project_file = find_project_file(args.project)
    project_dir = project_file.parent

    # ── 扫描模块 ──
    all_modules = get_test_modules(project_dir, config["testModulePattern"])
    if not all_modules:
        _error_exit(f"未找到匹配的测试模块：{config['testModulePattern']}")

    modules = filter_modules(
        all_modules, normalized_scopes, project_dir, config["moduleCategories"]
    )
    if not modules:
        _error_exit(f"没有模块匹配 scope：{normalized_scopes}")

    _color_print(f"待运行的测试模块：{', '.join(modules)}", _COLOR_GREEN)

    # ── 编译项目 ──
    if not args.skip_build:
        invoke_build(project_file, args.config)

    # ── 解析引擎 ──
    engine_path = resolve_engine_path(project_file)

    # ── 逐模块运行测试 ──
    all_results = invoke_test_run(
        project_file, engine_path, modules, config, project_dir,
        normalized_scopes, args.no_null_rhi,
    )

    # ── 保存合并结果 ──
    results_path = save_results(all_results, project_dir)
    _color_print(f"结果已保存至：{results_path}", _COLOR_GREEN)

    # ── 生成报告 ──
    report_script = _SCRIPT_DIR / "report.py"
    if report_script.exists():
        subprocess.run(
            [
                sys.executable,
                str(report_script),
                "--results", str(results_path),
                "--project-dir", str(project_dir),
            ],
            check=False,
        )

    # ── 按失败数确定退出码 ──
    return 1 if all_results["overall"]["failed"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Generic Unreal Engine 5 project build script
=============================================
Auto-detect project file, resolve engine path, and build UE5 C++ project.
Supports both Launcher-installed and source-built engines.

Usage:
    python build.py
    python build.py --config Debug
    python build.py --project "D:/Projects/MyGame/MyGame.uproject"
    python build.py -h

Exit codes:
    0   Build succeeded
    1   Script error (project not found, engine not resolved, etc.)
    N   Build.bat exit code (propagated)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import winreg
from pathlib import Path
from typing import Optional

# ── ANSI 颜色代码 ─────────────────────────────────────────────────────────────
_COLOR_CYAN    = "\033[36m"
_COLOR_GREEN   = "\033[32m"
_COLOR_YELLOW  = "\033[33m"
_COLOR_RED     = "\033[31m"
_COLOR_RESET   = "\033[0m"


def _color_print(msg: str, color: str = _COLOR_RESET) -> None:
    """如果终端支持，则使用 ANSI 颜色打印。"""
    if sys.stdout.isatty():
        print(f"{color}{msg}{_COLOR_RESET}")
    else:
        print(msg)


def _error_exit(msg: str, code: int = 1) -> None:
    """打印错误信息并以指定退出码终止。"""
    _color_print(msg, _COLOR_RED)
    sys.exit(code)


# ── 1. 项目发现 ─────────────────────────────────────────────────────────────
def find_project_file(explicit_path: str) -> Path:
    """从显式路径或当前工作目录自动检测 .uproject 文件。"""
    if explicit_path:
        p = Path(explicit_path).resolve()
        if not p.exists():
            _error_exit(f"项目路径不存在：{explicit_path}")
        return p

    cwd = Path.cwd()
    uproject_files = list(cwd.glob("*.uproject"))

    if not uproject_files:
        _error_exit(
            "当前目录未找到 .uproject 文件。"
            "请通过 --project 参数指定项目路径：--project \"路径\\项目.uproject\""
        )

    if len(uproject_files) == 1:
        return uproject_files[0].resolve()

    # 发现多个项目
    _color_print("发现多个 UE5 项目：", _COLOR_YELLOW)
    for i, f in enumerate(uproject_files):
        _color_print(f"  [{i}] {f.name}", _COLOR_CYAN)
    _color_print(
        "请使用 --project 参数指定要编译的项目",
        _COLOR_YELLOW,
    )
    sys.exit(1)


# ── 2. 引擎路径解析 ─────────────────────────────────────────────────────────
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


# ── 3. 目标名称推导 ─────────────────────────────────────────────────────────
def get_build_target(project_file: Path) -> str:
    """根据项目文件名推导编辑器编译目标。"""
    project_name = project_file.stem
    return f"{project_name}Editor"


# ── 4. 编译执行 ───────────────────────────────────────────────────────────────
def run_build(build_bat: Path, target: str, platform: str, configuration: str, project_file: Path) -> int:
    """调用 Build.bat 并返回其退出码。"""
    cmd = [
        str(build_bat),
        target,
        platform,
        configuration,
        str(project_file),
        "-waitmutex",
    ]

    _color_print("执行命令：", _COLOR_CYAN)
    _color_print(f"  {' '.join(cmd)}", _COLOR_CYAN)

    try:
        # 从 config.yaml 读取的超时时间（30 分钟）
        result = subprocess.run(cmd, check=False, timeout=30 * 60)
        return result.returncode
    except FileNotFoundError:
        _error_exit(f"Build.bat 未找到或无法执行：{build_bat}")
    except subprocess.TimeoutExpired:
        _error_exit("编译超时（30 分钟），请检查是否有进程阻塞或死锁。")
    except OSError as exc:
        _error_exit(f"执行 Build.bat 失败：{exc}")
    # 不可达，但满足类型检查器
    return 1  # pragma: no cover


# ── 主流程 ───────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(
        description="通用 Unreal Engine 5 项目编译脚本",
        epilog="示例：python build.py --config Debug",
    )
    parser.add_argument(
        "--project", "-p",
        metavar="路径",
        default="",
        help=".uproject 文件路径（可选，默认从当前目录自动检测）",
    )
    parser.add_argument(
        "--config", "-c",
        choices=["Development", "Debug", "Shipping", "Test"],
        default="Development",
        help="编译配置（默认：Development）",
    )
    parser.add_argument(
        "--platform", "-pl",
        choices=["Win64"],
        default="Win64",
        help="目标平台（默认：Win64）",
    )
    args = parser.parse_args()

    # ── 发现项目 ──
    project_file = find_project_file(args.project)

    # ── 解析引擎 ──
    engine_path = resolve_engine_path(project_file)

    # ── 推导目标 ──
    target = get_build_target(project_file)

    # ── 验证 Build.bat ──
    build_bat = engine_path / "Engine" / "Build" / "BatchFiles" / "Build.bat"
    if not build_bat.exists():
        _error_exit(f"Build.bat 未找到：{build_bat}")

    # ── 打印编译摘要 ──
    _color_print("=" * 44, _COLOR_CYAN)
    _color_print("Unreal Engine 5 项目编译", _COLOR_CYAN)
    _color_print("=" * 44, _COLOR_CYAN)
    print(f"项目：      {project_file}")
    print(f"目标：      {target}")
    print(f"平台：      {args.platform}")
    print(f"配置：      {args.config}")
    print(f"引擎：      {engine_path}")
    _color_print("=" * 44, _COLOR_CYAN)

    # ── 执行编译 ──
    exit_code = run_build(build_bat, target, args.platform, args.config, project_file)

    if exit_code != 0:
        _color_print(f"编译失败，退出码：{exit_code}", _COLOR_RED)
        return exit_code

    _color_print("=" * 44, _COLOR_GREEN)
    _color_print("编译成功！", _COLOR_GREEN)
    _color_print("=" * 44, _COLOR_GREEN)
    return 0


if __name__ == "__main__":
    sys.exit(main())

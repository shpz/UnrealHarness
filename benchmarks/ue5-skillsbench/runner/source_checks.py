"""Shared source-inspection helpers for task verifiers."""
from __future__ import annotations

import re


def strip_c_comments(text: str) -> str:
    """Remove C/C++/C# style comments so tokens inside comments are ignored."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"/\*.*", "", text)
    text = re.sub(r"//.*", "", text)
    return text


def target_includes_module(target_text: str, module_name: str) -> bool:
    """Check that a Target.cs registers a module via Add or AddRange.

    Tolerates whitespace variations and ignores commented-out code, unlike a
    literal 'ExtraModuleNames.Add("X")' substring match.
    """
    text = strip_c_comments(target_text)
    escaped = re.escape(module_name)
    if re.search(rf'ExtraModuleNames\s*\.\s*Add\s*\(\s*"{escaped}"\s*\)', text):
        return True
    for match in re.finditer(r"ExtraModuleNames\s*\.\s*AddRange\s*\(([^;]*)\)", text, re.DOTALL):
        if re.search(rf'"{escaped}"', match.group(1)):
            return True
    return False


def target_references_module(target_text: str, module_name: str) -> bool:
    """Check whether a Target.cs mentions a module outside of comments."""
    return re.search(rf"\b{re.escape(module_name)}\b", strip_c_comments(target_text)) is not None

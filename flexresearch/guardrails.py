"""Deterministic safety checks for untrusted retrieved text.

Retrieved PDFs, notes and manuals are evidence, never executable instructions.
These checks are intentionally conservative: a suspicious chunk remains stored
and citeable locally, but it is withheld from an external model prompt.
"""

from __future__ import annotations

import re
from typing import Any


_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "instruction_override",
        re.compile(
            r"(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:previous|prior|system|developer)\s+(?:instructions?|prompts?|rules?)"
            r"|(?:忽略|无视|覆盖|绕过).{0,16}(?:之前|先前|系统|开发者).{0,8}(?:指令|提示|规则)",
            re.IGNORECASE,
        ),
    ),
    (
        "secret_exfiltration",
        re.compile(
            r"(?:reveal|print|show|return|exfiltrat\w*)\s+(?:the\s+)?(?:api[_ -]?key|password|secret|token|system\s+prompt)"
            r"|(?:泄露|显示|输出|返回|窃取).{0,12}(?:api\s*key|密钥|密码|令牌|系统提示)",
            re.IGNORECASE,
        ),
    ),
    (
        "tool_or_command_injection",
        re.compile(
            r"(?:execute|run|call)\s+(?:this\s+)?(?:shell\s+)?(?:command|tool|function)"
            r"|(?:执行|调用).{0,8}(?:命令|工具|函数).{0,20}(?:不要告诉|without telling)",
            re.IGNORECASE,
        ),
    ),
)


def prompt_injection_reasons(text: str) -> list[str]:
    """Return stable reason codes for instruction-like retrieved content."""
    return [reason for reason, pattern in _INJECTION_PATTERNS if pattern.search(text)]


def partition_model_evidence(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split retrieved chunks into model-safe and locally-visible blocked items."""
    safe: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for item in items:
        reasons = prompt_injection_reasons(str(item.get("excerpt", "")))
        if reasons:
            blocked.append({**item, "promptInjectionReasons": reasons})
        else:
            safe.append(item)
    return safe, blocked


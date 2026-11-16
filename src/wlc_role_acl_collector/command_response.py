"""Recognize standalone CLI rejection messages without scanning policy prose."""
from __future__ import annotations

import re

_REJECTION = re.compile(
    r"^(?:%\s*)?(?:Error:\s*)?(?:"
    r"Invalid (?:input|command)\b|Unknown command\b|"
    r"Incomplete command\b|Ambiguous command\b|"
    r"Permission denied\b|Access denied\b|Not authorized\b|"
    r"You do not have permission to execute this command$|"
    r"Authorization (?:failed|failure)\b|Command authorization failed\b|"
    r"Insufficient privileges\b|Command not (?:found|supported)\b"
    r")", re.IGNORECASE,
)


def cli_rejection(output: str) -> str | None:
    """Return the first recognized CLI error line, or None for ordinary output."""
    for line in output.splitlines():
        if _REJECTION.match(line.strip()):
            return line.strip()
    return None

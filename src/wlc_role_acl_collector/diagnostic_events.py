"""Safe diagnostic event model.

Events are designed for reports that can leave the company network. Store
stage, code, status, and command IDs only; never store raw command output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .diagnostic_codes import DIAGNOSTIC_CODES, DiagnosticCode, get_diagnostic_code
from .redaction import redact_payload, redact_sensitive_text


@dataclass
class DiagnosticEvent:
    stage: str
    status: str
    code: str
    message: str
    command_id: str = ""
    detail: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        payload = redact_payload(
            {
                "timestamp": self.timestamp,
                "stage": self.stage,
                "status": self.status,
                "code": self.code,
                "command_id": self.command_id,
                "message": self.message,
                "detail": self.detail,
            }
        )
        # Only this structured field may retain an exact registered code. The
        # same token in arbitrary message/detail text remains hostname-redacted.
        if self.code in DIAGNOSTIC_CODES:
            payload["code"] = self.code
        return payload


def event_from_code(
    code: str | DiagnosticCode,
    *,
    status: str = "error",
    command_id: str = "",
    detail: str = "",
) -> DiagnosticEvent:
    diagnostic_code = code if isinstance(code, DiagnosticCode) else get_diagnostic_code(code)
    return DiagnosticEvent(
        stage=diagnostic_code.stage,
        status=status,
        code=diagnostic_code.code,
        command_id=command_id,
        message=diagnostic_code.safe_message,
        detail=redact_sensitive_text(detail),
    )


def safe_info_event(stage: str, message: str, *, command_id: str = "", detail: str = "") -> DiagnosticEvent:
    return DiagnosticEvent(
        stage=stage,
        status="ok",
        code="OK",
        command_id=command_id,
        message=redact_sensitive_text(message),
        detail=redact_sensitive_text(detail),
    )

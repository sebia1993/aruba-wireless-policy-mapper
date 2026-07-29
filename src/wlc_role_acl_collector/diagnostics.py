from __future__ import annotations

from dataclasses import dataclass

from .diagnostic_codes import classify_message_to_code
from .models import CollectionResult


@dataclass(frozen=True)
class FailureInfo:
    category: str
    title: str
    detail: str
    suggestion: str
    code: str = "WLC-UNK-001"

    def as_text(self) -> str:
        return f"{self.title}\n\n오류 코드: {self.code}\n\n{self.detail}\n\n{self.suggestion}"


def classify_error_message(message: str) -> FailureInfo:
    diagnostic_code = classify_message_to_code(message)
    normalized = message.lower()

    if diagnostic_code.code == "WLC-AUTH-002":
        return FailureInfo(
            category="enable_authentication",
            title="Enable 권한 전환에 실패했습니다",
            detail=message or "로그인은 성공했지만 enable 모드로 전환하지 못했습니다.",
            suggestion="이 계정에 enable password가 필요한지, 입력값과 권한이 올바른지 확인하세요.",
            code=diagnostic_code.code,
        )

    if any(token in normalized for token in ("authentication", "auth", "password", "login failed")):
        return FailureInfo(
            category="authentication",
            title="WLC 로그인 인증에 실패했습니다",
            detail=message or "The WLC rejected the login.",
            suggestion=(
                "ID/PW, 계정 잠금 상태, 선택한 SSH/Telnet 방식으로 로그인할 권한이 있는지 확인하세요."
            ),
            code=diagnostic_code.code,
        )

    if any(
        token in normalized
        for token in (
            "timed out",
            "timeout",
            "tcp connection",
            "connection refused",
            "unreachable",
            "no route",
            "port",
            "firewall",
        )
    ):
        return FailureInfo(
            category="timeout",
            title="WLC에 연결하지 못했습니다",
            detail=message or "The WLC did not respond on the selected IP/port.",
            suggestion=(
                "WLC IP, 프로토콜, 포트, 라우팅, 방화벽과 장비의 SSH/Telnet 활성화 상태를 확인하세요."
            ),
            code=diagnostic_code.code,
        )

    if any(token in normalized for token in ("show configuration effective", "invalid input", "permission", "denied")):
        return FailureInfo(
            category="command",
            title="로그인 후 필수 조회 명령에 실패했습니다",
            detail=message or "Login succeeded, but the required command output was not collected.",
            suggestion=(
                "WLC 계정에 'show configuration effective'와 'show rights <role>' 조회 권한이 있는지 확인하세요."
            ),
            code=diagnostic_code.code,
        )

    return FailureInfo(
        category="unknown",
        title="수집을 완료하지 못했습니다",
        detail=message or "The collection failed before a report could be generated.",
        suggestion="결과 폴더의 run.log를 확인하고, 원인을 알 수 없으면 안전 진단을 실행하세요.",
        code=diagnostic_code.code,
    )


def summarize_collection_failure(result: CollectionResult) -> FailureInfo:
    failed_commands = [command for command in result.commands if command.error]
    for command_id in ("connect", "configuration_effective"):
        for command in failed_commands:
            if command.command_id == command_id:
                return classify_error_message(command.error)

    if not result.command_output("configuration_effective"):
        return classify_error_message("show configuration effective output was not collected.")

    if failed_commands:
        return classify_error_message("; ".join(command.error for command in failed_commands))

    return classify_error_message("")

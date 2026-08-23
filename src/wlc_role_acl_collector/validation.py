"""Shared validation limits used by CLI, GUI, web, and config loading."""

from __future__ import annotations

import ipaddress
import re


MIN_COMMAND_TIMEOUT_SECONDS = 5
MAX_COMMAND_TIMEOUT_SECONDS = 600
MAX_COLLECTION_DURATION_SECONDS = 60 * 60
_HOST_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_AOS_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/+\- ]{0,127}$")
_AOS_UNQUOTED_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/+\-]{0,127}$")


def validate_wlc_address(value: object) -> str:
    address = str(value or "").strip()
    if not address:
        raise ValueError("WLC IP를 입력하세요.")
    if len(address) > 253 or any(character.isspace() for character in address):
        raise ValueError("WLC IP 또는 Host 형식이 올바르지 않습니다.")
    if "://" in address or any(character in address for character in "/\\?#"):
        raise ValueError("WLC IP 또는 Host만 입력하세요. URL이나 경로는 사용할 수 없습니다.")

    try:
        ipaddress.ip_address(address)
        return address
    except ValueError:
        pass

    hostname = address[:-1] if address.endswith(".") else address
    labels = hostname.split(".")
    if not hostname or any(not _HOST_LABEL_PATTERN.fullmatch(label) for label in labels):
        raise ValueError("WLC IP 또는 Host 형식이 올바르지 않습니다. 예: 10.10.10.10")
    return address


def validate_port(value: object) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Port는 숫자로 입력하세요.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("Port는 1에서 65535 사이여야 합니다.")
    return port


def validate_timeout_seconds(value: object) -> int:
    try:
        timeout = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Timeout seconds는 숫자로 입력하세요.") from exc
    if not MIN_COMMAND_TIMEOUT_SECONDS <= timeout <= MAX_COMMAND_TIMEOUT_SECONDS:
        raise ValueError(
            f"Timeout seconds는 {MIN_COMMAND_TIMEOUT_SECONDS}에서 "
            f"{MAX_COMMAND_TIMEOUT_SECONDS} 사이여야 합니다."
        )
    return timeout


def validate_aos_identifier(value: object, *, kind: str) -> str:
    """AOS 객체 이름을 CLI 인자로 안전하게 사용할 수 있는지 확인합니다."""

    identifier = str(value or "")
    if identifier != identifier.strip() or not _AOS_IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(f"안전하지 않은 {kind} 이름을 감지해 동적 조회 명령을 차단했습니다.")
    return identifier


def build_show_netdestination_command(alias: object) -> str:
    return _build_show_identifier_command("show netdestination", alias, kind="Alias")


def build_show_rights_command(role: object) -> str:
    return _build_show_identifier_command("show rights", role, kind="Role")


def _build_show_identifier_command(prefix: str, value: object, *, kind: str) -> str:
    identifier = validate_aos_identifier(value, kind=kind)
    if _AOS_UNQUOTED_IDENTIFIER_PATTERN.fullmatch(identifier):
        return f"{prefix} {identifier}"
    return f'{prefix} "{identifier}"'

"""SHA2-only key exchange와 앱 전용 host-key pinning을 Netmiko에 적용합니다."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import paramiko

from .hostkeys import check_pinned_key


class PinnedHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    """Paramiko가 인증을 시작하기 전에 앱 전용 known_hosts를 직접 검증합니다."""

    def __init__(self, known_hosts_path: Path) -> None:
        self.known_hosts_path = known_hosts_path

    def missing_host_key(self, client: paramiko.SSHClient, hostname: str, key: paramiko.PKey) -> None:
        del client
        state = check_pinned_key(
            hostname,
            key,
            known_hosts_path=self.known_hosts_path,
        )
        if state == "trusted":
            return
        if state == "unknown":
            raise paramiko.SSHException(
                "미승인 SSH 서버 키입니다. trust-host-key로 지문을 확인하고 먼저 승인하세요."
            )
        raise paramiko.SSHException("승인된 SSH 서버 키와 현재 키가 달라 연결을 차단했습니다.")


def build_pinned_ssh_client(known_hosts_path: Path) -> paramiko.SSHClient:
    """키 파일을 Paramiko에 직접 로드하지 않아 RSA/SHA-1 재활성화를 막습니다."""

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(PinnedHostKeyPolicy(known_hosts_path))
    return client


class _PinnedHostKeyConnectionMixin:
    def _build_ssh_client(self) -> paramiko.SSHClient:
        return build_pinned_ssh_client(Path(self.alt_key_file))


@lru_cache(maxsize=None)
def _connection_class(device_type: str):
    from netmiko.ssh_dispatcher import CLASS_MAPPER

    base_class = CLASS_MAPPER.get(device_type)
    if base_class is None:
        raise ValueError(f"지원되지 않는 SSH device_type입니다: {device_type}")
    class_name = "Pinned" + "".join(part.title() for part in device_type.replace("-", "_").split("_"))
    return type(class_name, (_PinnedHostKeyConnectionMixin, base_class), {})


def connect_with_pinned_host_key(**params: Any):
    """Netmiko 장비 class를 host-key pinning mixin과 결합해 연결합니다."""

    device_type = str(params.pop("device_type", "")).strip()
    if not device_type or not bool(params.get("ssh_strict")):
        raise ValueError("SSH strict host-key 검증 설정이 필요합니다.")
    if params.get("system_host_keys") is not False:
        raise ValueError("앱 전용 known_hosts만 사용해야 합니다.")
    if not bool(params.get("alt_host_keys")) or not str(params.get("alt_key_file") or ""):
        raise ValueError("앱 전용 known_hosts 경로가 필요합니다.")
    connection_class = _connection_class(device_type)
    return connection_class(**params)

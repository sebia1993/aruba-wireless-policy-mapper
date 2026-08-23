"""SSH 서버 키를 자격 증명 전 확인하고 앱 전용 known_hosts에 고정합니다."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import socket
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


def hardened_disabled_algorithms() -> dict[str, list[str]]:
    """Paramiko 4.0의 RSA/SHA-1 경로를 모든 SSH 연결에서 차단합니다."""

    return {"keys": ["ssh-rsa"], "pubkeys": ["ssh-rsa"]}


@dataclass(frozen=True)
class HostKeyObservation:
    host: str
    port: int
    key_type: str
    fingerprint: str
    key: Any = field(repr=False, compare=False)

    @property
    def lookup_name(self) -> str:
        return self.host if self.port == 22 else f"[{self.host}]:{self.port}"


def default_known_hosts_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "ArubaWirelessPolicyMapper" / "known_hosts"
    return Path.home() / ".local" / "share" / "ArubaWirelessPolicyMapper" / "known_hosts"


def sha256_fingerprint(key_bytes: bytes) -> str:
    encoded = base64.b64encode(hashlib.sha256(key_bytes).digest()).decode("ascii").rstrip("=")
    return f"SHA256:{encoded}"


def probe_host_key(host: str, port: int, *, timeout: float = 15.0) -> HostKeyObservation:
    """로그인 정보를 보내기 전에 SSH 서버 키만 가져옵니다."""

    try:
        import paramiko
    except ImportError as exc:  # pragma: no cover - 패키지 의존성 보호
        raise RuntimeError("SSH 서버 키 확인에 Paramiko가 필요합니다.") from exc

    connection: socket.socket | None = None
    transport: Any | None = None
    try:
        connection = socket.create_connection((host, port), timeout=timeout)
        connection.settimeout(timeout)
        transport = paramiko.Transport(
            connection,
            disabled_algorithms=hardened_disabled_algorithms(),
        )
        transport.start_client(timeout=timeout)
        key = transport.get_remote_server_key()
        return HostKeyObservation(
            host=host,
            port=port,
            key_type=key.get_name(),
            fingerprint=sha256_fingerprint(key.asbytes()),
            key=key,
        )
    except (EOFError, OSError, paramiko.SSHException) as exc:
        raise RuntimeError("SSH 서버 키를 안전하게 확인하지 못했습니다.") from exc
    finally:
        if transport is not None:
            transport.close()
        if connection is not None:
            connection.close()


def check_host_key(
    observation: HostKeyObservation,
    *,
    known_hosts_path: Path | None = None,
) -> str:
    """`trusted`, `unknown`, `changed` 중 하나를 반환합니다."""

    return check_pinned_key(
        observation.lookup_name,
        observation.key,
        known_hosts_path=known_hosts_path,
    )


def check_pinned_key(
    lookup_name: str,
    key: Any,
    *,
    known_hosts_path: Path | None = None,
) -> str:
    """주어진 endpoint의 키 재료를 앱 전용 known_hosts와 비교합니다."""

    host_keys = _load_host_keys(known_hosts_path or default_known_hosts_path())
    entry = host_keys.lookup(lookup_name)
    if not entry:
        return "unknown"
    for stored in entry.values():
        if hmac.compare_digest(stored.asbytes(), key.asbytes()):
            return "trusted"
    return "changed"


def approve_unknown_host_key(
    observation: HostKeyObservation,
    *,
    known_hosts_path: Path | None = None,
) -> Path:
    """검토한 최초 키만 추가하며 기존 키는 자동 교체하지 않습니다."""

    path = known_hosts_path or default_known_hosts_path()
    state = check_host_key(observation, known_hosts_path=path)
    if state == "trusted":
        return path
    if state == "changed":
        raise RuntimeError("승인된 SSH 서버 키와 현재 키가 달라 저장을 차단했습니다.")

    host_keys = _load_host_keys(path)
    host_keys.add(observation.lookup_name, observation.key_type, observation.key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
        host_keys.save(temp_name)
        Path(temp_name).replace(path)
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)
    return path


def trust_host_key_interactive(
    host: str,
    port: int,
    *,
    timeout: float = 15.0,
    known_hosts_path: Path | None = None,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> Path:
    observation = probe_host_key(host, port, timeout=timeout)
    path = known_hosts_path or default_known_hosts_path()
    state = check_host_key(observation, known_hosts_path=path)
    output_func(f"대상: {observation.lookup_name}")
    output_func(f"키 형식: {observation.key_type}")
    output_func(f"SHA-256 지문: {observation.fingerprint}")
    if state == "trusted":
        output_func("이미 승인된 SSH 서버 키와 일치합니다.")
        return path
    if state == "changed":
        raise RuntimeError("승인된 SSH 서버 키와 현재 키가 달라 연결을 차단했습니다.")
    answer = input_func("별도 관리 경로로 지문을 확인했다면 TRUST를 입력하세요: ").strip()
    if answer != "TRUST":
        raise PermissionError("SSH 서버 키를 승인하지 않았습니다.")
    approve_unknown_host_key(observation, known_hosts_path=path)
    output_func(f"앱 전용 known_hosts에 저장했습니다: {path}")
    return path


def _load_host_keys(path: Path):
    try:
        import paramiko
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("SSH 서버 키 확인에 Paramiko가 필요합니다.") from exc

    host_keys = paramiko.HostKeys()
    if not path.exists():
        return host_keys
    try:
        host_keys.load(str(path))
    except (OSError, ValueError, paramiko.SSHException) as exc:
        raise RuntimeError("앱 전용 known_hosts를 안전하게 읽지 못했습니다.") from exc
    return host_keys

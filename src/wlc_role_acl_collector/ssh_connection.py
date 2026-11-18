"""SHA2-only key exchange와 앱 전용 host-key pinning을 Netmiko에 적용합니다."""

from __future__ import annotations

import threading
import time
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
                "미승인 SSH 서버 키입니다. GUI 또는 Web의 SHA-256 지문 확인창에서 먼저 승인하세요."
            )
        raise paramiko.SSHException("승인된 SSH 서버 키와 현재 키가 달라 연결을 차단했습니다.")


class SSHSetupCancelled(RuntimeError):
    """The user cancelled before SSH shell preparation completed."""


class SSHSetupDeadlineExceeded(RuntimeError):
    """The SSH setup budget expired before shell preparation completed."""


def _setup_error(
    deadline: float, cancel_event: threading.Event | None
) -> RuntimeError | None:
    if cancel_event is not None and cancel_event.is_set():
        return SSHSetupCancelled("SSH setup cancelled by user.")
    if time.monotonic() >= deadline:
        return SSHSetupDeadlineExceeded("SSH setup timeout: deadline exceeded.")
    return None


class _BoundedSSHClient(paramiko.SSHClient):
    def __init__(self, deadline: float, cancel_event: threading.Event | None):
        super().__init__()
        self._setup_deadline = deadline
        self._setup_cancel_event = cancel_event

    def invoke_shell(self, *args, **kwargs):
        # Paramiko's get_pty()/invoke_shell() wait on events without a timeout;
        # channel.settimeout() does not affect those waits. Closing the transport
        # releases channel-open and channel-request events. The caller performs
        # the actual connection work synchronously; only this small guard runs
        # in a thread, and it is always joined before returning/raising.
        error = _setup_error(self._setup_deadline, self._setup_cancel_event)
        if error is not None:
            raise error
        finished = threading.Event()
        interrupted: list[Exception] = []

        def guard():
            while not finished.is_set():
                error = _setup_error(self._setup_deadline, self._setup_cancel_event)
                if error is not None:
                    interrupted.append(error)
                    try:
                        self.close()
                    except Exception:
                        # Preserve the interruption reason; constructor cleanup
                        # retries closing any resources still owned by Netmiko.
                        pass
                    return
                finished.wait(min(0.05, max(0, self._setup_deadline - time.monotonic())))

        watcher = threading.Thread(target=guard, name="ssh-setup-guard")
        watcher.start()
        try:
            try:
                channel = super().invoke_shell(*args, **kwargs)
            finally:
                finished.set()
                watcher.join()
        except Exception:
            if interrupted:
                raise interrupted[0] from None
            raise
        # Join first: an interruption racing with shell success must raise,
        # never return a connection that the guard can later close.
        if interrupted:
            raise interrupted[0]
        error = _setup_error(self._setup_deadline, self._setup_cancel_event)
        if error is not None:
            raise error
        return channel


def build_pinned_ssh_client(
    known_hosts_path: Path,
    *,
    _deadline: float | None = None,
    _cancel_event: threading.Event | None = None,
) -> paramiko.SSHClient:
    """키 파일을 Paramiko에 직접 로드하지 않아 RSA/SHA-1 재활성화를 막습니다."""

    client = _BoundedSSHClient(
        time.monotonic() + 60 if _deadline is None else _deadline, _cancel_event
    )
    client.set_missing_host_key_policy(PinnedHostKeyPolicy(known_hosts_path))
    return client


class _PinnedHostKeyConnectionMixin:
    def __init__(
        self, *, _deadline: float | None = None,
        _cancel_event: threading.Event | None = None, **params: Any,
    ):
        setup_deadline = time.monotonic() + float(params.get("timeout", 60))
        self._setup_deadline = min(setup_deadline, _deadline) if _deadline is not None else setup_deadline
        self._setup_cancel_event = _cancel_event
        try:
            super().__init__(**params)
        except BaseException:
            self._close_failed_connection()
            raise

    def _close_failed_connection(self):
        # Do not run device-specific disconnect()/cleanup() commands on an
        # incomplete session. Close the transport before the channel so channel
        # close cannot wait for a remote acknowledgement or key exchange.
        for name in ("remote_conn_pre", "remote_conn", "session_log"):
            resource = getattr(self, name, None)
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    pass
        secrets_filter = getattr(self, "_secrets_filter", None)
        if secrets_filter is not None:
            from netmiko.base_connection import log

            log.removeFilter(secrets_filter)

    def _build_ssh_client(self) -> paramiko.SSHClient:
        return build_pinned_ssh_client(
            Path(self.alt_key_file),
            _deadline=self._setup_deadline,
            _cancel_event=self._setup_cancel_event,
        )


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

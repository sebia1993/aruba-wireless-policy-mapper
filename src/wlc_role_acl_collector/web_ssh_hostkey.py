"""Credential-free SSH host-key preflight for the local Streamlit frontend.

The collector's pinned SSH policy remains the final authority at authentication.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from pathlib import Path

from .hostkeys import (
    HostKeyObservation,
    approve_unknown_host_key,
    check_host_key,
    probe_host_key,
)
from .validation import validate_port, validate_timeout_seconds, validate_wlc_address


@dataclass(frozen=True)
class WebSSHHostKeyReview:
    observation: HostKeyObservation
    state: str


def inspect_ssh_host_key(
    host: str,
    port: int,
    *,
    timeout: int = 60,
    known_hosts_path: Path | None = None,
) -> WebSSHHostKeyReview:
    """Probe before authentication and classify against the GUI's same key store."""
    validated_host = validate_wlc_address(host)
    validated_port = validate_port(port)
    validated_timeout = validate_timeout_seconds(timeout)
    observation = probe_host_key(
        validated_host,
        validated_port,
        timeout=min(15.0, float(validated_timeout)),
    )
    if observation.host != validated_host or observation.port != validated_port:
        raise RuntimeError("확인한 SSH 서버 키의 접속 대상이 요청 대상과 다릅니다.")
    state = check_host_key(observation, known_hosts_path=known_hosts_path)
    if state not in {"trusted", "unknown", "changed"}:
        raise RuntimeError("SSH 서버 키 승인 상태를 확인할 수 없습니다.")
    return WebSSHHostKeyReview(observation=observation, state=state)


def approve_reviewed_ssh_host_key(
    review: WebSSHHostKeyReview,
    *,
    host: str,
    port: int,
    timeout: int = 60,
    known_hosts_path: Path | None = None,
) -> Path:
    """Only pin an explicitly reviewed, still-identical first-seen server key."""
    if review.state != "unknown":
        raise PermissionError("최초 확인한 미승인 SSH 서버 키만 승인할 수 있습니다.")

    validated_host = validate_wlc_address(host)
    validated_port = validate_port(port)
    if (
        validated_host != review.observation.host
        or validated_port != review.observation.port
    ):
        raise PermissionError("접속 대상 또는 포트가 변경되어 지문 확인을 다시 해야 합니다.")

    # An operator may take time to verify the displayed fingerprint.
    # Probe again and fail closed if the server has changed meanwhile.
    fresh = inspect_ssh_host_key(
        validated_host,
        validated_port,
        timeout=timeout,
        known_hosts_path=known_hosts_path,
    )
    if (
        fresh.state == "changed"
        or fresh.observation.key_type != review.observation.key_type
        or not hmac.compare_digest(
            fresh.observation.key.asbytes(), review.observation.key.asbytes()
        )
    ):
        raise RuntimeError("표시한 SSH 서버 키와 현재 서버 키가 달라 승인을 차단했습니다.")

    # The existing atomic, locked host-key writer rejects conflicting approvals.
    return approve_unknown_host_key(
        review.observation, known_hosts_path=known_hosts_path
    )

"""No credentials or real WLC are required to test Web SSH key confirmation."""

import pytest

from wlc_role_acl_collector import web_ssh_hostkey
from wlc_role_acl_collector.hostkeys import (
    HostKeyObservation,
    check_host_key,
    sha256_fingerprint,
)


def _observation(key, host="192.0.2.10", port=22):
    return HostKeyObservation(
        host=host,
        port=port,
        key_type=key.get_name(),
        fingerprint=sha256_fingerprint(key.asbytes()),
        key=key,
    )


def test_first_contact_can_be_explicitly_approved_and_reused(monkeypatch, tmp_path):
    paramiko = pytest.importorskip("paramiko")
    known_hosts = tmp_path / "known_hosts"
    observed = _observation(paramiko.RSAKey.generate(1024), port=2222)
    monkeypatch.setattr(web_ssh_hostkey, "probe_host_key", lambda *_args, **_kwargs: observed)
    args = dict(host="192.0.2.10", port=2222, known_hosts_path=known_hosts)

    initial = web_ssh_hostkey.inspect_ssh_host_key(**args)
    assert initial.state == "unknown"
    assert not known_hosts.exists()

    web_ssh_hostkey.approve_reviewed_ssh_host_key(initial, **args)
    assert check_host_key(observed, known_hosts_path=known_hosts) == "trusted"
    assert web_ssh_hostkey.inspect_ssh_host_key(**args).state == "trusted"
    with pytest.raises(PermissionError):
        web_ssh_hostkey.approve_reviewed_ssh_host_key(
            web_ssh_hostkey.inspect_ssh_host_key(**args), **args
        )


def test_changed_between_review_and_confirmation_is_rejected(monkeypatch, tmp_path):
    paramiko = pytest.importorskip("paramiko")
    known_hosts = tmp_path / "known_hosts"
    original = _observation(paramiko.RSAKey.generate(1024))
    replacement = _observation(paramiko.RSAKey.generate(1024))
    current = [original]
    monkeypatch.setattr(web_ssh_hostkey, "probe_host_key", lambda *_args, **_kwargs: current[0])
    args = dict(host="192.0.2.10", port=22, known_hosts_path=known_hosts)

    review = web_ssh_hostkey.inspect_ssh_host_key(**args)
    current[0] = replacement
    with pytest.raises(RuntimeError, match="달라"):
        web_ssh_hostkey.approve_reviewed_ssh_host_key(review, **args)
    assert not known_hosts.exists()


def test_changed_pinned_key_is_always_blocked(monkeypatch, tmp_path):
    paramiko = pytest.importorskip("paramiko")
    known_hosts = tmp_path / "known_hosts"
    original = _observation(paramiko.RSAKey.generate(1024))
    current = [original]
    monkeypatch.setattr(web_ssh_hostkey, "probe_host_key", lambda *_args, **_kwargs: current[0])
    args = dict(host="192.0.2.10", port=22, known_hosts_path=known_hosts)
    web_ssh_hostkey.approve_reviewed_ssh_host_key(
        web_ssh_hostkey.inspect_ssh_host_key(**args), **args
    )

    current[0] = _observation(paramiko.RSAKey.generate(1024))
    changed = web_ssh_hostkey.inspect_ssh_host_key(**args)
    assert changed.state == "changed"
    with pytest.raises(PermissionError):
        web_ssh_hostkey.approve_reviewed_ssh_host_key(changed, **args)
    assert check_host_key(original, known_hosts_path=known_hosts) == "trusted"


def test_different_target_or_port_is_rejected_without_network_probe(monkeypatch):
    paramiko = pytest.importorskip("paramiko")
    original = _observation(paramiko.RSAKey.generate(1024))
    review = web_ssh_hostkey.WebSSHHostKeyReview(original, "unknown")
    monkeypatch.setattr(
        web_ssh_hostkey, "probe_host_key",
        lambda *_args, **_kwargs: pytest.fail("changed endpoint must not be probed"),
    )
    with pytest.raises(PermissionError, match="변경"):
        web_ssh_hostkey.approve_reviewed_ssh_host_key(
            review, host="192.0.2.11", port=22
        )
    with pytest.raises(PermissionError, match="변경"):
        web_ssh_hostkey.approve_reviewed_ssh_host_key(
            review, host="192.0.2.10", port=2222
        )


def test_invalid_target_timeout_is_rejected_before_probe(monkeypatch):
    monkeypatch.setattr(
        web_ssh_hostkey, "probe_host_key",
        lambda *_args, **_kwargs: pytest.fail("invalid input must not be probed"),
    )
    with pytest.raises(ValueError):
        web_ssh_hostkey.inspect_ssh_host_key("https://192.0.2.10", 22)
    with pytest.raises(ValueError):
        web_ssh_hostkey.inspect_ssh_host_key("192.0.2.10", 22, timeout=1000)

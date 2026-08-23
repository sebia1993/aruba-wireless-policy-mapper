import pytest

import wlc_role_acl_collector.hostkeys as hostkeys
from wlc_role_acl_collector.hostkeys import HostKeyObservation


def _observation(key, *, host="192.0.2.10", port=22):
    return HostKeyObservation(
        host=host,
        port=port,
        key_type=key.get_name(),
        fingerprint=hostkeys.sha256_fingerprint(key.asbytes()),
        key=key,
    )


def test_known_hosts_approves_unknown_and_blocks_changed_key(tmp_path):
    paramiko = pytest.importorskip("paramiko")
    path = tmp_path / "known_hosts"
    first = _observation(paramiko.RSAKey.generate(1024))
    changed = _observation(paramiko.RSAKey.generate(1024))

    assert hostkeys.check_host_key(first, known_hosts_path=path) == "unknown"
    assert hostkeys.approve_unknown_host_key(first, known_hosts_path=path) == path
    assert hostkeys.check_host_key(first, known_hosts_path=path) == "trusted"
    assert hostkeys.check_host_key(changed, known_hosts_path=path) == "changed"
    with pytest.raises(RuntimeError, match="달라"):
        hostkeys.approve_unknown_host_key(changed, known_hosts_path=path)


def test_nonstandard_port_uses_openssh_endpoint_form():
    paramiko = pytest.importorskip("paramiko")
    observation = _observation(paramiko.RSAKey.generate(1024), port=2222)
    assert observation.lookup_name == "[192.0.2.10]:2222"


def test_interactive_trust_requires_exact_confirmation(monkeypatch, tmp_path):
    paramiko = pytest.importorskip("paramiko")
    observation = _observation(paramiko.RSAKey.generate(1024))
    monkeypatch.setattr(hostkeys, "probe_host_key", lambda *_args, **_kwargs: observation)
    path = tmp_path / "known_hosts"

    with pytest.raises(PermissionError, match="승인하지"):
        hostkeys.trust_host_key_interactive(
            observation.host,
            observation.port,
            known_hosts_path=path,
            input_func=lambda _prompt: "yes",
            output_func=lambda _line: None,
        )
    assert not path.exists()

    hostkeys.trust_host_key_interactive(
        observation.host,
        observation.port,
        known_hosts_path=path,
        input_func=lambda _prompt: "TRUST",
        output_func=lambda _line: None,
    )
    assert hostkeys.check_host_key(observation, known_hosts_path=path) == "trusted"


def test_probe_disables_rsa_sha1_before_key_exchange(monkeypatch):
    paramiko = pytest.importorskip("paramiko")
    captured = {}

    class FakeConnection:
        def settimeout(self, timeout):
            captured["timeout"] = timeout

        def close(self):
            captured["socket_closed"] = True

    class FakeKey:
        def get_name(self):
            return "ssh-ed25519"

        def asbytes(self):
            return b"synthetic-host-key"

    class FakeTransport:
        def __init__(self, connection, *, disabled_algorithms):
            captured["connection"] = connection
            captured["disabled_algorithms"] = disabled_algorithms

        def start_client(self, *, timeout):
            captured["start_timeout"] = timeout

        def get_remote_server_key(self):
            return FakeKey()

        def close(self):
            captured["transport_closed"] = True

    fake_connection = FakeConnection()
    monkeypatch.setattr(hostkeys.socket, "create_connection", lambda *_args, **_kwargs: fake_connection)
    monkeypatch.setattr(paramiko, "Transport", FakeTransport)

    observation = hostkeys.probe_host_key("192.0.2.10", 22, timeout=7)

    assert observation.key_type == "ssh-ed25519"
    assert captured["disabled_algorithms"] == {
        "keys": ["ssh-rsa"],
        "pubkeys": ["ssh-rsa"],
    }
    assert captured["transport_closed"] is True
    assert captured["socket_closed"] is True

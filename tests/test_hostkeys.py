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


def _approve_in_process(path, key_text, host, loaded, release, done, results, ready):
    """Spawn-safe worker; pause one writer immediately before publishing its snapshot."""
    import base64
    import paramiko
    from pathlib import Path
    original = paramiko.HostKeys.save

    def save(keys, filename):
        if loaded is not None:
            loaded.set()
            if not release.wait(5):
                raise RuntimeError("test writer release timed out")
        return original(keys, filename)

    paramiko.HostKeys.save = save
    ready.set()
    try:
        key = paramiko.RSAKey(data=base64.b64decode(key_text))
        hostkeys.approve_unknown_host_key(_observation(key, host=host), known_hosts_path=Path(path))
        results.put("approved")
    except Exception as exc:
        results.put(str(exc))
    finally:
        done.set()


@pytest.mark.parametrize("same_endpoint", [False, True])
def test_concurrent_process_approvals_serialize_and_recheck_current_key(tmp_path, same_endpoint):
    import multiprocessing
    import paramiko
    context = multiprocessing.get_context("spawn")
    path = tmp_path / "known_hosts"
    first = _observation(paramiko.RSAKey.generate(1024))
    second = _observation(paramiko.RSAKey.generate(1024), host=first.host if same_endpoint else "192.0.2.11")
    loaded, release, first_done, second_done = [context.Event() for _ in range(4)]
    first_result, second_result = context.Queue(), context.Queue()
    first_ready, second_ready = context.Event(), context.Event()
    writer1 = context.Process(target=_approve_in_process, args=(str(path), first.key.get_base64(), first.host, loaded, release, first_done, first_result, first_ready))
    writer2 = context.Process(target=_approve_in_process, args=(str(path), second.key.get_base64(), second.host, None, release, second_done, second_result, second_ready))
    writer1.start()
    try:
        assert loaded.wait(5)
        writer2.start()
        assert second_ready.wait(5)
        overlapped = second_done.wait(0.4)
    finally:
        release.set()
        writer1.join(5)
        if writer2.pid is not None:
            writer2.join(5)
        for writer in (writer1, writer2):
            if writer.is_alive():
                writer.terminate()
                writer.join()
    assert writer1.exitcode == writer2.exitcode == 0
    assert not overlapped, "Second process must wait for the first complete update"
    assert first_result.get(timeout=1) == "approved"
    outcome = second_result.get(timeout=1)
    assert hostkeys.check_host_key(first, known_hosts_path=path) == "trusted"
    if same_endpoint:
        assert "달라" in outcome
        assert hostkeys.check_host_key(second, known_hosts_path=path) == "changed"
    else:
        assert outcome == "approved"
        assert hostkeys.check_host_key(second, known_hosts_path=path) == "trusted"

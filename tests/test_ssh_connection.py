import paramiko
import pytest

from wlc_role_acl_collector.hostkeys import approve_unknown_host_key
from wlc_role_acl_collector.hostkeys import HostKeyObservation, sha256_fingerprint
from wlc_role_acl_collector.ssh_connection import PinnedHostKeyPolicy, build_pinned_ssh_client


def _observation(key, *, host="192.0.2.10", port=22):
    return HostKeyObservation(
        host=host,
        port=port,
        key_type=key.get_name(),
        fingerprint=sha256_fingerprint(key.asbytes()),
        key=key,
    )


def test_pinned_policy_accepts_only_matching_key_material(tmp_path):
    known_hosts = tmp_path / "known_hosts"
    approved = paramiko.RSAKey.generate(1024)
    changed = paramiko.RSAKey.generate(1024)
    approve_unknown_host_key(_observation(approved), known_hosts_path=known_hosts)
    policy = PinnedHostKeyPolicy(known_hosts)

    policy.missing_host_key(paramiko.SSHClient(), "192.0.2.10", approved)
    with pytest.raises(paramiko.SSHException, match="달라"):
        policy.missing_host_key(paramiko.SSHClient(), "192.0.2.10", changed)
    with pytest.raises(paramiko.SSHException, match="미승인"):
        policy.missing_host_key(paramiko.SSHClient(), "192.0.2.11", approved)


def test_pinned_client_does_not_load_rsa_key_into_paramiko_priority_list(tmp_path):
    known_hosts = tmp_path / "known_hosts"
    approved = paramiko.RSAKey.generate(1024)
    approve_unknown_host_key(_observation(approved), known_hosts_path=known_hosts)

    client = build_pinned_ssh_client(known_hosts)

    assert not client.get_host_keys()
    assert isinstance(client._policy, PinnedHostKeyPolicy)


def _strict_params(path):
    return dict(device_type="synthetic", ssh_strict=True, system_host_keys=False,
                alt_host_keys=True, alt_key_file=str(path), timeout=1)


@pytest.mark.parametrize("stage", ["channel", "pty", "shell"])
@pytest.mark.parametrize("stop", ["deadline", "cancel"])
def test_stalled_shell_setup_is_bounded_and_closes_transport(monkeypatch, tmp_path, stage, stop):
    """Exercise Paramiko's real blocking channel event, without a real device."""
    import threading
    import time
    import wlc_role_acl_collector.ssh_connection as ssh

    cancelled = threading.Event()
    closed = threading.Event()
    entered = threading.Event()
    channel = paramiko.Channel(0)
    channel.active = True

    class Transport:
        def open_session(self, **kwargs):
            if stage == "channel":
                entered.set()
                closed.wait(2)
                raise paramiko.SSHException("closed")
            return channel

        def _send_user_message(self, message):
            if stage == "pty" or (stage == "shell" and self.requests == 1):
                entered.set()
            else:
                channel.event_ready = True
                channel.event.set()
            self.requests += 1

        def close(self):
            closed.set()
            channel._unlink()

        def _unlink_channel(self, channel_id):
            pass

        def get_exception(self):
            return None

        requests = 0

    transport = Transport()
    channel.transport = transport

    class Base:
        def __init__(self, **params):
            assert "_deadline" not in params
            assert "_cancel_event" not in params
            self.alt_key_file = params["alt_key_file"]
            self.remote_conn_pre = self._build_ssh_client()
            self.remote_conn_pre._transport = transport
            self.remote_conn = self.remote_conn_pre.invoke_shell()

    connection_type = type("SyntheticConnection", (ssh._PinnedHostKeyConnectionMixin, Base), {})
    monkeypatch.setattr(ssh, "_connection_class", lambda _kind: connection_type)
    # A safety timer also makes the old, unbounded implementation terminate.
    release = threading.Timer(0.8, transport.close)
    release.start()
    cancellation = threading.Timer(0.08, cancelled.set)
    if stop == "cancel":
        cancellation.start()
    started = time.monotonic()
    try:
        with pytest.raises(Exception) as error:
            ssh.connect_with_pinned_host_key(
                **_strict_params(tmp_path / "known_hosts"),
                _deadline=started + (0.08 if stop == "deadline" else 5),
                _cancel_event=cancelled,
            )
        elapsed = time.monotonic() - started
        assert entered.is_set(), "The test must reach the stalled operation"
        assert elapsed < 0.5
        assert closed.is_set()
        assert "cancel" in str(error.value).lower() if stop == "cancel" else "deadline" in str(error.value).lower()
        assert not any(t.name.startswith("ssh-setup-guard") for t in threading.enumerate())
    finally:
        release.cancel()
        release.join()
        if stop == "cancel":
            cancellation.join()


def test_constructor_failure_closes_partially_created_client_and_keeps_original_error(monkeypatch, tmp_path):
    import wlc_role_acl_collector.ssh_connection as ssh

    closed = []
    primary = RuntimeError("synthetic preparation failed")

    class Client:
        def close(self):
            closed.append(True)
            raise RuntimeError("cleanup failed")

    class Base:
        def __init__(self, **params):
            self.remote_conn_pre = Client()
            raise primary

    connection_type = type("SyntheticConnection", (ssh._PinnedHostKeyConnectionMixin, Base), {})
    monkeypatch.setattr(ssh, "_connection_class", lambda _kind: connection_type)
    with pytest.raises(RuntimeError) as error:
        ssh.connect_with_pinned_host_key(**_strict_params(tmp_path / "known_hosts"))
    assert error.value is primary
    assert closed == [True]


@pytest.mark.parametrize("stage", ["channel", "pty", "shell"])
def test_real_paramiko_stalled_requests_close_socket_and_stop_guard(tmp_path, stage):
    """A local socketpair server withholds replies; no device/network is used."""
    import socket
    import threading
    import time
    from wlc_role_acl_collector.ssh_connection import SSHSetupDeadlineExceeded

    server_socket, client_socket = socket.socketpair()
    release = threading.Event()
    entered = threading.Event()
    host_key = paramiko.RSAKey.generate(1024)
    path = tmp_path / "known_hosts"
    approve_unknown_host_key(_observation(host_key), known_hosts_path=path)

    class Server(paramiko.ServerInterface):
        def check_auth_password(self, username, password):
            return paramiko.AUTH_SUCCESSFUL

        def check_channel_request(self, kind, channel_id):
            if stage == "channel":
                entered.set()
                release.wait(3)
            return paramiko.OPEN_SUCCEEDED

        def check_channel_pty_request(self, channel, *args):
            if stage == "pty":
                entered.set()
                release.wait(3)
            return True

        def check_channel_shell_request(self, channel):
            if stage == "shell":
                entered.set()
                release.wait(3)
            return True

    server = paramiko.Transport(server_socket)
    server.add_server_key(host_key)
    client = build_pinned_ssh_client(path)
    server.start_server(event=threading.Event(), server=Server())
    try:
        client.connect("192.0.2.10", username="synthetic", password="synthetic",
                       sock=client_socket, allow_agent=False, look_for_keys=False)
        transport = client.get_transport()
        # Authentication is outside the deliberately short request-stall test
        # budget; slow CI hosts must first reach the operation under test.
        client._setup_deadline = time.monotonic() + 0.6
        started = time.monotonic()
        with pytest.raises(SSHSetupDeadlineExceeded):
            client.invoke_shell()
        assert entered.is_set()
        assert time.monotonic() - started < 1.5
        assert not transport.is_active()
        assert client_socket.fileno() == -1
        assert not any(t.name.startswith("ssh-setup-guard") for t in threading.enumerate())
        transport.join(1)
        assert not transport.is_alive()
    finally:
        release.set()
        client.close()
        server.close()
        server.join(2)
        client_socket.close()
        server_socket.close()


def test_successful_shell_has_no_late_guard_close(monkeypatch, tmp_path):
    import threading
    import time

    cancelled = threading.Event()
    sentinel = object()
    closed = []
    monkeypatch.setattr(paramiko.SSHClient, "invoke_shell", lambda *a, **kw: sentinel)
    client = build_pinned_ssh_client(tmp_path / "known_hosts", _deadline=time.monotonic() + 1,
                                     _cancel_event=cancelled)
    monkeypatch.setattr(client, "close", lambda: closed.append(True))
    assert client.invoke_shell() is sentinel
    cancelled.set()
    assert not any(t.name.startswith("ssh-setup-guard") for t in threading.enumerate())
    assert closed == []

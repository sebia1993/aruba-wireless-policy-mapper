import threading
from pathlib import Path

import wlc_role_acl_collector.collector as collector
from wlc_role_acl_collector.collector import collect_from_controller
from wlc_role_acl_collector.models import Controller, ControllerCredentials


FIXTURE = Path(__file__).parent / "fixtures" / "sample_controller" / "show_configuration_effective.txt"


class FakeConnection:
    def __init__(self, *, responses=None, failures=None, enable_failure=None, disconnect_failure=None):
        self.responses = responses or {}
        self.failures = failures or {}
        self.enable_failure = enable_failure
        self.disconnect_failure = disconnect_failure
        self.enable_called = False
        self.commands = []
        self.disconnected = False

    def enable(self):
        self.enable_called = True
        if self.enable_failure:
            raise self.enable_failure

    def send_command_timing(self, *, command_string, **_kwargs):
        self.commands.append(command_string)
        if command_string in self.failures:
            raise self.failures[command_string]
        return self.responses.get(command_string, "")

    def disconnect(self):
        self.disconnected = True
        if self.disconnect_failure:
            raise self.disconnect_failure


def _install_fake_netmiko(monkeypatch, connection):
    monkeypatch.setattr(
        collector,
        "_open_connection",
        lambda _params, *, protocol: connection,
    )


def test_collect_continues_when_disable_paging_fails(monkeypatch):
    config = FIXTURE.read_text(encoding="utf-8")
    connection = FakeConnection(
        responses={
            "show clock": "clock output",
            "show version": "version output",
            "show configuration effective": config,
            "show netdestination controller": "Name: controller\n1 host 10.10.10.1 32\n",
            "show rights corp-employee": "corp rights",
            "show rights guest-logon": "guest rights",
            "show rights logon": "logon rights",
        },
        failures={"no paging": RuntimeError("no paging is not supported")},
    )
    _install_fake_netmiko(monkeypatch, connection)
    events = []

    result = collect_from_controller(
        Controller(name="wlc", host="192.0.2.10"),
        credentials=ControllerCredentials(username="admin", password="secret"),
        progress_callback=lambda event, payload: events.append((event, payload)),
    )

    assert result.command_output("configuration_effective") == config
    assert any(command.command_id == "disable_paging" and not command.success for command in result.commands)
    assert not any(command.command_id == "connect" for command in result.commands)
    assert any(event == "roles_discovered" and payload["total"] == 3 for event, payload in events)
    assert any(event == "aliases_discovered" and payload["total"] == 1 for event, payload in events)
    assert "show netdestination controller" in connection.commands
    assert "show rights corp-employee" in connection.commands
    assert connection.disconnected is True


def test_collect_records_configuration_command_failure(monkeypatch):
    connection = FakeConnection(
        responses={"no paging": "", "show clock": "clock output", "show version": "version output"},
        failures={"show configuration effective": RuntimeError("Invalid input: show configuration effective")},
    )
    _install_fake_netmiko(monkeypatch, connection)
    events = []

    result = collect_from_controller(
        Controller(name="wlc", host="192.0.2.10"),
        credentials=ControllerCredentials(username="admin", password="secret"),
        progress_callback=lambda event, payload: events.append((event, payload)),
    )

    failed = [command for command in result.commands if not command.success]
    assert [(command.command_id, command.command) for command in failed] == [
        ("configuration_effective", "show configuration effective")
    ]
    assert not any(command.command_id == "connect" for command in result.commands)
    assert not any(command.startswith("show rights") for command in connection.commands)
    assert any(
        event == "command_error" and payload["command_id"] == "configuration_effective"
        for event, payload in events
    )


def test_collect_records_enable_password_failure_and_continues(monkeypatch):
    config = FIXTURE.read_text(encoding="utf-8")
    connection = FakeConnection(
        responses={
            "no paging": "",
            "show clock": "clock output",
            "show version": "version output",
            "show configuration effective": config,
            "show ip interface brief": "ip interface output",
            "show user-table": "user table output",
            "show netdestination controller": "Name: controller\n1 host 10.10.10.1 32\n",
            "show rights corp-employee": "corp rights",
            "show rights guest-logon": "guest rights",
            "show rights logon": "logon rights",
        },
        enable_failure=RuntimeError("enable denied"),
    )
    _install_fake_netmiko(monkeypatch, connection)
    events = []

    result = collect_from_controller(
        Controller(name="wlc", host="192.0.2.10"),
        credentials=ControllerCredentials(username="admin", password="secret", enable_password="bad"),
        progress_callback=lambda event, payload: events.append((event, payload)),
    )

    enable = next(command for command in result.commands if command.command_id == "enable")
    assert connection.enable_called is True
    assert enable.success is False
    assert "enable denied" in enable.error
    assert result.command_output("configuration_effective") == config
    assert any(
        event == "command_error" and payload["command_id"] == "enable" and "enable denied" in payload["error"]
        for event, payload in events
    )
    assert "show rights corp-employee" in connection.commands


def test_collect_cancellation_stops_before_next_command_and_disconnects(monkeypatch):
    cancel_event = threading.Event()

    class CancellingConnection(FakeConnection):
        def send_command_timing(self, *, command_string, **kwargs):
            output = super().send_command_timing(command_string=command_string, **kwargs)
            if command_string == "show clock":
                cancel_event.set()
            return output

    connection = CancellingConnection(
        responses={
            "no paging": "",
            "show clock": "clock output",
        }
    )
    _install_fake_netmiko(monkeypatch, connection)
    events = []

    result = collect_from_controller(
        Controller(name="wlc", host="192.0.2.10"),
        credentials=ControllerCredentials(username="admin", password="secret"),
        progress_callback=lambda event, payload: events.append((event, payload)),
        cancel_event=cancel_event,
    )

    assert connection.commands == ["no paging", "show clock"]
    assert any(command.command_id == "cancelled" for command in result.commands)
    assert any(event == "cancelled" for event, _payload in events)
    assert connection.disconnected is True


def test_collect_duration_limit_stops_before_first_command_and_disconnects(monkeypatch):
    connection = FakeConnection()
    _install_fake_netmiko(monkeypatch, connection)
    times = iter((0.0, 2.0))
    monkeypatch.setattr(collector.time, "monotonic", lambda: next(times))
    events = []

    result = collect_from_controller(
        Controller(name="wlc", host="192.0.2.10"),
        credentials=ControllerCredentials(username="admin", password="secret"),
        progress_callback=lambda event, payload: events.append((event, payload)),
        max_duration_seconds=1,
    )

    duration_failure = next(command for command in result.commands if command.command_id == "duration_limit")
    assert duration_failure.success is False
    assert connection.commands == []
    assert any(event == "duration_limit" for event, _payload in events)
    assert connection.disconnected is True


def test_collect_records_disconnect_failure_without_losing_collected_data(monkeypatch):
    config = FIXTURE.read_text(encoding="utf-8")
    connection = FakeConnection(
        responses={
            "show configuration effective": config,
            "show netdestination controller": "Name: controller\n1 host 10.10.10.1 32\n",
        },
        disconnect_failure=RuntimeError("socket cleanup failed"),
    )
    _install_fake_netmiko(monkeypatch, connection)

    result = collect_from_controller(
        Controller(name="wlc", host="192.0.2.10"),
        credentials=ControllerCredentials(username="admin", password="secret"),
    )

    disconnect = next(command for command in result.commands if command.command_id == "disconnect")
    assert result.command_output("configuration_effective") == config
    assert disconnect.success is False
    assert disconnect.error == "socket cleanup failed"
    assert connection.disconnected is True


def test_collect_rejects_timeout_outside_shared_api_contract():
    try:
        collect_from_controller(
            Controller(name="wlc", host="192.0.2.10"),
            credentials=ControllerCredentials(username="admin", password="secret"),
            timeout=601,
        )
    except ValueError as exc:
        assert "5에서 600" in str(exc)
    else:
        raise AssertionError("Expected timeout validation error")


def test_ssh_connect_params_require_app_known_hosts_and_telnet_does_not(tmp_path):
    credentials = ControllerCredentials(username="admin", password="secret")
    known_hosts = tmp_path / "known_hosts"

    ssh_params = collector._build_connect_params(
        controller=Controller(name="ssh", host="192.0.2.10", protocol="ssh"),
        credentials=credentials,
        timeout=30,
        known_hosts_path=known_hosts,
    )
    assert ssh_params["ssh_strict"] is True
    assert ssh_params["system_host_keys"] is False
    assert ssh_params["alt_host_keys"] is True
    assert ssh_params["alt_key_file"] == str(known_hosts)
    assert ssh_params["disabled_algorithms"] == {
        "keys": ["ssh-rsa"],
        "pubkeys": ["ssh-rsa"],
    }

    telnet_params = collector._build_connect_params(
        controller=Controller(
            name="telnet",
            host="192.0.2.10",
            protocol="telnet",
            port=23,
            device_type="generic_telnet",
        ),
        credentials=credentials,
        timeout=30,
        known_hosts_path=known_hosts,
    )
    assert "ssh_strict" not in telnet_params
    assert "alt_key_file" not in telnet_params
    assert "disabled_algorithms" not in telnet_params


def test_collect_never_sends_unsafe_discovered_alias(monkeypatch):
    connection = FakeConnection(
        responses={
            "show configuration effective": "synthetic config",
        }
    )
    _install_fake_netmiko(monkeypatch, connection)
    monkeypatch.setattr(collector, "discover_aliases_from_config", lambda _output: ['corp"; reload'])

    result = collect_from_controller(
        Controller(name="wlc", host="192.0.2.10"),
        credentials=ControllerCredentials(username="admin", password="secret"),
    )

    assert any(command.command_id == "invalid_netdestination_identifier" for command in result.commands)
    assert not any("reload" in command for command in connection.commands)


def test_credentials_repr_does_not_expose_secrets():
    credentials = ControllerCredentials(
        username="portfolio-user",
        password="secret-password",
        enable_password="secret-enable",
    )
    rendered = repr(credentials)
    assert "secret-password" not in rendered
    assert "secret-enable" not in rendered

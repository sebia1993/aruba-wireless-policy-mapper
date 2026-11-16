"""Synthetic wire regressions: collector outcomes, not Netmiko call arguments."""
import queue
import threading

import pytest
from netmiko import BaseConnection
from netmiko.aruba import ArubaOsSSH
import netmiko.base_connection as netmiko_base

import wlc_role_acl_collector.collector as collector
from wlc_role_acl_collector.collection_health import assess_collection_results
from wlc_role_acl_collector.gui_app import WlcRoleAclCollectorGui
from wlc_role_acl_collector.gui_support import GuiConnectionInput, build_target_from_gui_input
from wlc_role_acl_collector.models import Controller, ControllerCredentials

PROMPT = '(synthetic.wlc+1) [node] #'
CONFIG = 'wlan ssid-profile synthetic\n essid synthetic\nip access-list session synthetic-acl\n any alias synthetic-alias any permit\nuser-role synthetic-role\n'


class Clock:
    now = 0.0

    def time(self):
        return self.now

    monotonic = time

    def sleep(self, seconds):
        self.now += seconds


class Wire:
    def __init__(self, clock, responses=None, cancel=None):
        self.clock = clock
        self.responses = responses or {}
        self.cancel = cancel
        self.pending = []
        self.commands = []
        self.closed = False

    def write_channel(self, data):
        command = data.strip()
        if not command:
            self.pending.append((self.clock.now, PROMPT))
            return
        self.commands.append(command)
        response = self.responses.get(command, CONFIG if command == 'show configuration effective' else 'synthetic data')
        if self.cancel and command == 'show configuration effective':
            self.cancel.set()
        chunks = response if isinstance(response, list) else [(0, command + '\n' + response + '\n' + PROMPT)]
        self.pending.extend((self.clock.now + delay, text) for delay, text in chunks)

    def read_channel(self):
        ready = [text for when, text in self.pending if when <= self.clock.now]
        self.pending[:] = [(when, text) for when, text in self.pending if when > self.clock.now]
        return ''.join(ready)

    def close(self):
        self.closed = True


@pytest.fixture
def wire_connection(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(netmiko_base, 'time', clock)
    monkeypatch.setattr(collector, 'time', clock)

    def build(responses=None, cancel=None, connection_class=BaseConnection):
        connection = connection_class(host='192.0.2.10', auto_connect=False)
        connection.base_prompt = PROMPT[:-1]
        wire = Wire(clock, responses, cancel)
        connection.channel = wire
        connection.disconnect = wire.close
        monkeypatch.setattr(collector, '_open_connection', lambda *_args, **_kwargs: connection)
        return connection, wire, clock
    return build


def collect(**kwargs):
    return collector.collect_from_controller(
        Controller(name='synthetic', host='192.0.2.10'),
        credentials=ControllerCredentials(username='synthetic', password='synthetic'),
        timeout=5, **kwargs)


@pytest.mark.parametrize('command,command_id,status', [
    ('show configuration effective', 'configuration_effective', 'failed'),
    ('show user-table', 'user_table', 'partial'),
    ('show rights synthetic-role', 'rights::synthetic-role', 'partial'),
    ('show netdestination synthetic-alias', 'netdestination::synthetic-alias', 'partial'),
])
@pytest.mark.parametrize('rejection', [
    "% Invalid input detected at '^' marker.",
    'Error: Permission denied',
    '% Incomplete command.',
    '% Ambiguous command: show',
    'Unknown command: show',
])
def test_cli_rejection_is_failed_with_raw_evidence(wire_connection, command, command_id, status, rejection):
    _, wire, _ = wire_connection({command: rejection})
    result = collect()
    response = next(item for item in result.commands if item.command_id == command_id)
    assert response.success is False
    assert rejection in response.output
    assert rejection in response.error
    assert assess_collection_results([result]).status == status
    assert wire.closed


def test_error_words_in_config_are_successful_data(wire_connection):
    config = CONFIG + ' description "Error: Permission denied; invalid input; unknown command"\n'
    wire_connection({'show configuration effective': config})
    result = collect()
    assert config in result.command_output('configuration_effective')
    assert assess_collection_results([result]).status == 'completed'


def test_delayed_tail_is_in_correct_command_and_not_next_response(wire_connection):
    connection, _, clock = wire_connection({'show configuration effective': [
        (0, 'show configuration effective\nwlan ssid-profile first\n'),
        (2.5, ' essid delayed-tail\n' + PROMPT),
    ]})
    configuration = collector._run_command(connection, 'show configuration effective', timeout=5)
    returned_at = clock.now
    interfaces = collector._run_command(connection, 'show ip interface brief', timeout=5)
    assert 'essid delayed-tail' in configuration
    assert configuration.endswith(PROMPT)
    assert returned_at >= 2.5
    assert 'delayed-tail' not in interfaces


@pytest.mark.parametrize('tail', ['', '\n(other-wlc) #', '\n' + PROMPT + ' embedded text'])
def test_missing_actual_completion_prompt_stops_before_next_command(wire_connection, tail):
    _, wire, clock = wire_connection({'show clock': [(0, 'show clock\npartial clock data' + tail)]})
    result = collect()
    response = next(item for item in result.commands if item.command_id == 'clock')
    assert response.success is False
    assert 'partial clock data' in response.output
    assert wire.commands == ['no paging', 'show clock']
    assert wire.closed
    assert clock.now <= 5.1


def test_prompt_without_command_echo_does_not_complete(wire_connection):
    _, wire, _ = wire_connection({'show clock': [(0, '\n' + PROMPT)]})
    result = collect()
    assert not next(item for item in result.commands if item.command_id == 'clock').success
    assert wire.commands == ['no paging', 'show clock']


def test_cancel_during_required_timeout_records_cancel_and_cleanup(wire_connection):
    cancel = threading.Event()
    _, wire, _ = wire_connection({'show configuration effective': [(0, 'show configuration effective\npartial')] + [(i / 2, '\npartial') for i in range(1, 20)]}, cancel)
    result = collect(cancel_event=cancel)
    assert collector.collection_was_cancelled(result)
    assert not next(item for item in result.commands if item.command_id == 'configuration_effective').success
    assert wire.closed


@pytest.mark.parametrize('rejection,status', [('% Invalid input detected at marker.', 'failed'), (None, 'cancelled')])
def test_gui_terminal_state_reflects_required_rejection_or_cancel(wire_connection, tmp_path, rejection, status):
    app = object.__new__(WlcRoleAclCollectorGui)
    app.event_queue = queue.Queue()
    app.cancel_event = threading.Event()
    target = build_target_from_gui_input(GuiConnectionInput(host='192.0.2.10', username='synthetic', password='synthetic'))
    wire_connection({'show configuration effective': rejection if rejection else [(0, 'show configuration effective\npartial')] + [(i / 2, '\npartial') for i in range(1, 20)]},
                    None if rejection else app.cancel_event)
    app._run_collection_worker(target, tmp_path, 5, [])
    terminal = [(event, data) for event, data in app.event_queue.queue if event in ('done', 'error', 'cancelled')]
    assert len(terminal) == 1
    event, payload = terminal[0]
    if status == 'cancelled':
        assert event == 'cancelled'
        assert not list(tmp_path.rglob('report.html'))
    else:
        assert event == 'error'
        assert payload['run_log'].exists()
        assert not list(tmp_path.rglob('*.xlsx'))


def test_prompt_probe_is_bounded_and_never_sends_command_without_prompt(wire_connection):
    _, wire, clock = wire_connection()
    original_write = wire.write_channel

    def missing_prompt(data):
        if data.strip():
            original_write(data)

    wire.write_channel = missing_prompt
    result = collect()
    assert not result.commands[0].success
    assert wire.commands == []
    assert wire.closed
    assert clock.now <= 5.1


@pytest.mark.parametrize('command,command_id', [
    ('show netdestination synthetic-alias', 'netdestination::synthetic-alias'),
    ('show rights synthetic-role', 'rights::synthetic-role'),
])
def test_unframed_dynamic_response_stops_collection(wire_connection, command, command_id):
    _, wire, _ = wire_connection({command: [(0, command + '\npartial dynamic data')]})
    events = []
    result = collect(progress_callback=lambda event, payload: events.append(event))
    response = next(item for item in result.commands if item.command_id == command_id)
    assert not response.success
    assert 'partial dynamic data' in response.output
    assert 'complete' not in events
    assert wire.commands[-1] == command
    assert wire.closed


def test_aruba_autocomplete_echo_uses_device_supported_prompt_framing(wire_connection):
    connection, _, _ = wire_connection(
        {'show configuration effective': [(0, 'show configuration  effective\n' + CONFIG + PROMPT)]},
        connection_class=ArubaOsSSH,
    )
    output = collector._run_command(connection, 'show configuration effective', timeout=5)
    assert CONFIG in output
    assert output.endswith(PROMPT)


@pytest.mark.parametrize('denial', [
    'Error:You do not have permission to execute this command',
    'You do not have permission to execute this command',
])
@pytest.mark.parametrize('command,command_id,status', [
    ('show configuration effective', 'configuration_effective', 'failed'),
    ('show user-table', 'user_table', 'partial'),
])
def test_aruba_permission_denial_fails_with_raw_evidence(
    wire_connection, denial, command, command_id, status,
):
    _, wire, _ = wire_connection({command: denial}, connection_class=ArubaOsSSH)
    result = collect()
    response = next(item for item in result.commands if item.command_id == command_id)
    assert response.success is False
    assert denial in response.output
    assert denial in response.error
    assert assess_collection_results([result]).status == status
    assert wire.closed


@pytest.mark.parametrize('description', [
    'Error:You do not have permission to execute this command',
    'You do not have permission to execute this command',
])
def test_aruba_permission_words_in_description_are_successful_data(wire_connection, description):
    config = CONFIG + f' description "{description}"\n'
    wire_connection({'show configuration effective': config}, connection_class=ArubaOsSSH)
    result = collect()
    assert config in result.command_output('configuration_effective')
    assert assess_collection_results([result]).status == 'completed'

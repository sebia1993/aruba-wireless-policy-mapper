"""GUI SSH preflight: never use credentials until the operator confirms new keys."""
from __future__ import annotations

import queue
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import wlc_role_acl_collector.gui_app as gui_app
from wlc_role_acl_collector.gui_support import GuiConnectionInput, build_target_from_gui_input
from wlc_role_acl_collector.gui_app import WlcRoleAclCollectorGui


def _target(protocol="ssh"):
    return build_target_from_gui_input(
        GuiConnectionInput(
            host="192.0.2.10",
            port="22" if protocol == "ssh" else "23",
            protocol=protocol,
            username="test-account",
            password="not-a-real-password",
        )
    )


def _observation():
    return SimpleNamespace(
        host="192.0.2.10",
        port=22,
        key_type="ssh-ed25519",
        fingerprint="SHA256:synthetic-base64-fingerprint",
        lookup_name="192.0.2.10",
    )


def _app():
    app = object.__new__(WlcRoleAclCollectorGui)
    app.event_queue = queue.Queue()
    app.cancel_event = threading.Event()
    app.close_requested = False
    return app


@pytest.mark.parametrize("state", ["trusted", "unknown", "changed"])
def test_preflight_checks_key_in_background_before_authentication(monkeypatch, tmp_path, state):
    app = _app()
    observed = _observation()
    calls = []
    def probe(host, port, *, timeout):
        calls.append(("probe", host, port, timeout))
        return observed
    monkeypatch.setattr(gui_app, "probe_host_key", probe)
    monkeypatch.setattr(gui_app, "check_host_key", lambda key: (calls.append(("check", key)), state)[1])

    app._run_host_key_preflight_worker("collection", _target(), tmp_path, 60, [])
    output = list(app.event_queue.queue)
    ready = [payload for event, payload in output if event == "ssh_key_result"]
    assert len(ready) == 1
    assert ready[0]["state"] == state
    assert ready[0]["observation"] is observed
    assert ready[0]["kind"] == "collection"
    assert calls == [("probe", "192.0.2.10", 22, 15.0), ("check", observed)]


def test_trusted_key_resumes_without_any_dialog_or_approval(monkeypatch, tmp_path):
    app = _app()
    call_log = []
    monkeypatch.setattr(app, "_ask_host_key_approval", lambda obs: (_ for _ in ()).throw(AssertionError("unexpected dialog")))
    monkeypatch.setattr(gui_app, "approve_unknown_host_key", lambda obs: (_ for _ in ()).throw(AssertionError("unexpected trust")))
    monkeypatch.setattr(app, "_start_authenticated_worker", lambda *args: call_log.append(args))
    target = _target()
    app._apply_host_key_preflight({"kind": "collection", "target": target, "output_dir": tmp_path, "timeout": 60, "role_networks": [], "state": "trusted", "observation": _observation()})
    assert len(call_log) == 1
    assert call_log[0][1] is target


def test_unknown_key_requires_explicit_dialog_confirmation_before_auth(monkeypatch, tmp_path):
    app = _app()
    calls = []
    observed = _observation()
    target = _target()
    monkeypatch.setattr(app, "_ask_host_key_approval", lambda key: (calls.append("review"), True)[1])
    monkeypatch.setattr(gui_app, "approve_unknown_host_key", lambda key: (calls.append("approve"), tmp_path / "known_hosts")[1])
    monkeypatch.setattr(app, "_start_authenticated_worker", lambda *args: calls.append("authenticate"))
    app._apply_host_key_preflight({"kind": "diagnostic", "target": target, "output_dir": tmp_path, "timeout": 60, "role_networks": [], "state": "unknown", "observation": observed})
    assert calls == ["review", "approve", "authenticate"]


def test_declined_key_never_saves_key_or_sends_credentials(monkeypatch, tmp_path):
    app = _app()
    monkeypatch.setattr(app, "_ask_host_key_approval", lambda key: False)
    monkeypatch.setattr(gui_app, "approve_unknown_host_key", lambda key: pytest.fail("must not approve a denied key"))
    monkeypatch.setattr(app, "_start_authenticated_worker", lambda *args: pytest.fail("must not start SSH auth"))
    app._apply_host_key_preflight({"kind": "collection", "target": _target(), "output_dir": tmp_path, "timeout": 60, "role_networks": [], "state": "unknown", "observation": _observation()})
    assert list(app.event_queue.queue)[-1][0] == "cancelled"


def test_changed_key_is_blocked_without_dialog_or_authentication(monkeypatch, tmp_path):
    app = _app()
    monkeypatch.setattr(app, "_ask_host_key_approval", lambda key: pytest.fail("changed key must not offer approval"))
    monkeypatch.setattr(gui_app, "approve_unknown_host_key", lambda key: pytest.fail("changed key must not be approved"))
    monkeypatch.setattr(app, "_start_authenticated_worker", lambda *args: pytest.fail("changed key must not authenticate"))
    app._apply_host_key_preflight({"kind": "collection", "target": _target(), "output_dir": tmp_path, "timeout": 60, "role_networks": [], "state": "changed", "observation": _observation()})
    event, payload = app.event_queue.get_nowait()
    assert event == "error"
    assert "WLC-SEC-003" in payload["message"]


def test_cancel_during_key_probe_does_not_request_confirmation(monkeypatch, tmp_path):
    app = _app()
    observed = _observation()
    monkeypatch.setattr(gui_app, "probe_host_key", lambda *_args, **_kwargs: (app.cancel_event.set(), observed)[1])
    monkeypatch.setattr(gui_app, "check_host_key", lambda key: "unknown")
    app._run_host_key_preflight_worker("collection", _target(), tmp_path, 60, [])
    assert [event for event, _ in app.event_queue.queue][-1] == "cancelled"


def test_probe_error_is_informative_and_never_starts_auth(monkeypatch, tmp_path):
    app = _app()
    def fail(*_args, **_kwargs):
        raise RuntimeError("SSH 서버 키를 안전하게 확인하지 못했습니다.")
    monkeypatch.setattr(gui_app, "probe_host_key", fail)
    app._run_host_key_preflight_worker("diagnostic", _target(), tmp_path, 60, [])
    event, payload = list(app.event_queue.queue)[-1]
    assert event == "error"
    assert "WLC-SEC-004" in payload["message"]
    assert "password" not in payload["message"].lower()


def test_start_methods_preflight_ssh_but_not_telnet(monkeypatch, tmp_path):
    app = _app()
    app.is_running = False
    app.cancel_event = threading.Event()
    app.output_dir_var = SimpleNamespace(get=lambda: str(tmp_path))
    app.running_progress_title_var = SimpleNamespace(set=lambda *_: None)
    app._read_timeout = lambda: 60
    app._load_role_networks_for_selected_path = lambda: []
    app._set_running = lambda *_: None
    app._log = lambda *_: None
    recorded = []
    class FakeThread:
        def __init__(self, *, target, args, daemon):
            recorded.append((target.__name__, args, daemon))
        def start(self):
            pass
    monkeypatch.setattr(gui_app.threading, "Thread", FakeThread)
    for mode in ("ssh", "telnet"):
        app._read_form = lambda mode=mode: GuiConnectionInput(
            host="192.0.2.10", protocol=mode, username="operator", password="dummy"
        )
        app._start_collection()
        app._start_diagnostic()
    assert recorded[0][0] == "_run_host_key_preflight_worker"
    assert recorded[1][0] == "_run_host_key_preflight_worker"
    assert recorded[2][0] == "_run_collection_worker"
    assert recorded[3][0] == "_run_diagnostic_worker"

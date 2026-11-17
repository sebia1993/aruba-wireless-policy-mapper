"""Streamlit first-contact SSH host-key approval must precede authentication."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from wlc_role_acl_collector import web_ssh_hostkey, web_logic
from wlc_role_acl_collector.web_logic import WebArtifact, WebCollectionResult


APP_PATH = Path(__file__).parents[1] / "app.py"


def _review(state="unknown"):
    observation = SimpleNamespace(
        host="192.0.2.10",
        port=22,
        lookup_name="192.0.2.10",
        key_type="ssh-ed25519",
        fingerprint="SHA256:synthetic-fingerprint",
    )
    return web_ssh_hostkey.WebSSHHostKeyReview(observation, state)


@pytest.fixture
def prepared_app(monkeypatch):
    # Exercise the dialog content inline in AppTest, which cannot click a modal.
    monkeypatch.setattr(st, "dialog", lambda _title: lambda function: function, raising=False)
    calls = []
    monkeypatch.setattr(
        web_logic,
        "run_web_collection",
        lambda *_args, **_kwargs: (
            calls.append("collect"),
            WebCollectionResult(
                True, "synthetic-run", {}, [], [],
                artifacts={
                    key: WebArtifact(
                        f"synthetic.{key}", b"synthetic", "application/octet-stream"
                    )
                    for key in ("xlsx", "csv", "html")
                },
            ),
        )[1],
    )
    app = AppTest.from_file(str(APP_PATH)).run(timeout=20)
    next(item for item in app.text_input if item.label == "WLC IP").set_value("192.0.2.10")
    next(item for item in app.text_input if item.label == "장비 ID").set_value("operator")
    next(item for item in app.text_input if item.label == "장비 PW").set_value("synthetic")
    return app, calls


def test_unknown_key_shows_fingerprint_and_never_authenticates_early(monkeypatch, prepared_app):
    app, calls = prepared_app
    monkeypatch.setattr(web_ssh_hostkey, "inspect_ssh_host_key", lambda *_args, **_kwargs: _review())
    app.button[0].click().run(timeout=20)

    assert not app.exception
    assert calls == []
    assert "pending_web_ssh_host_key" in app.session_state
    assert any("SHA256:synthetic-fingerprint" in item.value for item in app.code)
    assert app.button(key="web_ssh_approve").disabled
    assert any("별도 관리 경로" in item.value for item in app.info)


def test_verified_approval_precedes_collection_and_clears_pending(monkeypatch, prepared_app):
    app, calls = prepared_app
    monkeypatch.setattr(web_ssh_hostkey, "inspect_ssh_host_key", lambda *_args, **_kwargs: _review())
    monkeypatch.setattr(
        web_ssh_hostkey,
        "approve_reviewed_ssh_host_key",
        lambda *_args, **_kwargs: (calls.append("approve"), Path("known_hosts"))[1],
    )
    app.button[0].click().run(timeout=20)
    app.checkbox(key="web_ssh_verified").set_value(True).run(timeout=20)
    app.button(key="web_ssh_approve").click().run(timeout=20)

    assert not app.exception
    assert calls == ["approve", "collect"]
    assert "pending_web_ssh_host_key" not in app.session_state
    assert app.session_state["last_result"].success


def test_rejected_first_key_never_pins_or_authenticates(monkeypatch, prepared_app):
    app, calls = prepared_app
    monkeypatch.setattr(web_ssh_hostkey, "inspect_ssh_host_key", lambda *_args, **_kwargs: _review())
    monkeypatch.setattr(
        web_ssh_hostkey, "approve_reviewed_ssh_host_key",
        lambda *_args, **_kwargs: pytest.fail("rejected key must not be saved"),
    )
    app.button[0].click().run(timeout=20)
    app.button(key="web_ssh_reject").click().run(timeout=20)

    assert not app.exception
    assert calls == []
    assert "pending_web_ssh_host_key" not in app.session_state


def test_changed_key_is_blocked_without_approval(monkeypatch, prepared_app):
    app, calls = prepared_app
    monkeypatch.setattr(web_ssh_hostkey, "inspect_ssh_host_key", lambda *_args, **_kwargs: _review("changed"))
    app.button[0].click().run(timeout=20)

    assert not app.exception
    assert calls == []
    assert "pending_web_ssh_host_key" not in app.session_state
    assert any("WLC-SEC-003" in item.value for item in app.error)


def test_trusted_key_collects_without_dialog(monkeypatch, prepared_app):
    app, calls = prepared_app
    monkeypatch.setattr(web_ssh_hostkey, "inspect_ssh_host_key", lambda *_args, **_kwargs: _review("trusted"))
    app.button[0].click().run(timeout=20)

    assert not app.exception
    assert calls == ["collect"]
    assert "pending_web_ssh_host_key" not in app.session_state


def test_switching_protocol_invalidates_pending_approval(monkeypatch, prepared_app):
    app, calls = prepared_app
    monkeypatch.setattr(web_ssh_hostkey, "inspect_ssh_host_key", lambda *_args, **_kwargs: _review())
    app.button[0].click().run(timeout=20)
    app.radio(key="connection_protocol").set_value("telnet").run(timeout=20)

    assert not app.exception
    assert calls == []
    assert "pending_web_ssh_host_key" not in app.session_state


def test_missing_credentials_never_probe_or_collect(monkeypatch):
    monkeypatch.setattr(st, "dialog", lambda _title: lambda function: function, raising=False)
    monkeypatch.setattr(
        web_ssh_hostkey, "inspect_ssh_host_key",
        lambda *_args, **_kwargs: pytest.fail("must validate input before probing"),
    )
    app = AppTest.from_file(str(APP_PATH)).run(timeout=20)
    next(item for item in app.text_input if item.label == "WLC IP").set_value("192.0.2.10")
    app.button[0].click().run(timeout=20)

    assert not app.exception
    assert any("Username" in item.value for item in app.error)

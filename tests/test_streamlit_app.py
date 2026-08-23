from pathlib import Path
import runpy

import pytest

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).parents[1] / "app.py"


def test_streamlit_connection_labels_and_protocol_default_ports():
    app = AppTest.from_file(str(APP_PATH)).run(timeout=20)

    assert not app.exception
    assert app.radio(key="connection_protocol").value == "ssh"
    assert app.number_input(key="connection_port_ssh").value == 22
    assert any(item.label == "WLC IP" for item in app.text_input)
    assert any(item.label == "장비 ID" for item in app.text_input)
    assert any(item.label == "장비 PW" for item in app.text_input)

    app.radio(key="connection_protocol").set_value("telnet").run(timeout=20)

    assert not app.exception
    assert app.number_input(key="connection_port_telnet").value == 23
    assert any("Telnet" in item.value and "자동 전환" in item.value for item in app.warning)


def test_streamlit_runtime_blocks_non_loopback_binding(monkeypatch):
    namespace = runpy.run_path(str(APP_PATH))
    streamlit_module = namespace["st"]
    stopped = RuntimeError("stopped")
    monkeypatch.setattr(streamlit_module, "get_option", lambda _name: "0.0.0.0")
    monkeypatch.setattr(streamlit_module, "error", lambda _message: None)
    monkeypatch.setattr(streamlit_module, "stop", lambda: (_ for _ in ()).throw(stopped))

    with pytest.raises(RuntimeError, match="stopped"):
        namespace["_enforce_loopback_binding"]()

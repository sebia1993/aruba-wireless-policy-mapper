from pathlib import Path

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

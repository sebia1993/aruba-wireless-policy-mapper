from pathlib import Path
import runpy
import shutil

import pytest

from streamlit.testing.v1 import AppTest
from wlc_role_acl_collector.web_logic import WebArtifact, WebCollectionResult
from wlc_role_acl_collector import web_ssh_hostkey


@pytest.fixture(autouse=True)
def _preapproved_ssh_for_existing_app_tests(monkeypatch):
    """These legacy tests exercise result retention, not host-key onboarding."""
    from types import SimpleNamespace

    monkeypatch.setattr(
        web_ssh_hostkey,
        "inspect_ssh_host_key",
        lambda *_args, **_kwargs: web_ssh_hostkey.WebSSHHostKeyReview(
            observation=SimpleNamespace(host="192.0.2.10", port=22),
            state="trusted",
        ),
    )


APP_PATH = Path(__file__).parents[1] / "app.py"


@pytest.mark.parametrize("portable", [False, True], ids=["source", "windows-portable"])
def test_sample_download_matches_workbook_accepted_by_uploader(tmp_path, monkeypatch, portable):
    import streamlit as st
    from wlc_role_acl_collector.role_networks import load_role_network_definitions_with_summary

    sample = APP_PATH.parent / "config" / "role_networks.example.xlsx"
    root = tmp_path / "web" if portable else tmp_path / "checkout"
    script_dir = root / "app" if portable else root
    script_dir.mkdir(parents=True)
    (root / "config").mkdir()
    shutil.copy2(APP_PATH, script_dir)
    shutil.copy2(sample, root / "config")
    monkeypatch.chdir(tmp_path)
    downloads = []
    download_button = st.download_button

    def capture(label, **kwargs):
        downloads.append(kwargs)
        return download_button(label, **kwargs)

    monkeypatch.setattr(st, "download_button", capture)
    app = AppTest.from_file(str(script_dir / "app.py")).run(timeout=20)
    assert not app.exception
    assert [btn.proto.label for btn in app.get("download_button")] == ["사내 Role 대역표 샘플 다운로드 (.xlsx)"]
    assert app.get("file_uploader")[0].proto.label == "사내 Role 대역표 Excel"
    (download,) = downloads
    assert download["file_name"] == sample.name
    assert download["mime"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert download["data"] == sample.read_bytes()
    received = tmp_path / download["file_name"]
    received.write_bytes(download["data"])
    loaded = load_role_network_definitions_with_summary(received)
    assert (loaded.sheet_name, loaded.role_count, loaded.network_count) == ("Role_Networks", 2, 3)


def _successful_web_result(run_id):
    return WebCollectionResult(
        success=True, run_id=run_id, summary={}, preview_rows=[], acl_preview_rows=[],
        artifacts={key: WebArtifact(f"{run_id}.{key}", f"{run_id}-{key}".encode(), "application/octet-stream")
                   for key in ("xlsx", "csv", "html")},
    )


@pytest.mark.parametrize("failure_kind", ["invalid", "busy", "exception", "failed_result"])
def test_streamlit_failed_retry_retains_previous_downloads(monkeypatch, failure_kind):
    from wlc_role_acl_collector import web_logic

    previous = _successful_web_result("previous-success")
    failed = WebCollectionResult(False, "failed-attempt", {}, [], [], error="synthetic failure")
    if failure_kind != "invalid":
        def fail_collection(*_args, **_kwargs):
            if failure_kind == "busy":
                raise web_logic.WebCollectionBusyError("synthetic target busy")
            if failure_kind == "exception":
                raise OSError("synthetic collection failure")
            return failed
        monkeypatch.setattr(web_logic, "run_web_collection", fail_collection)

    app = AppTest.from_file(str(APP_PATH))
    app.session_state["last_result"] = previous
    app.run(timeout=20)
    next(item for item in app.text_input if item.label == "WLC IP").set_value("https://192.0.2.10" if failure_kind == "invalid" else "192.0.2.10")
    next(item for item in app.text_input if item.label == "장비 ID").set_value("sample")
    next(item for item in app.text_input if item.label == "장비 PW").set_value("synthetic")
    app.button[0].click().run(timeout=20)

    assert not app.exception
    assert "last_result" in app.session_state
    assert app.session_state["last_result"].artifacts == previous.artifacts
    assert any("이전 성공 결과" in item.value for item in app.subheader)
    assert any("previous-success" in item.value for item in app.caption)
    assert len(app.get("download_button")) == 4  # Three result files plus the input template.
    if failure_kind == "failed_result":
        assert any("synthetic failure" in item.value for item in app.error)
    app.run(timeout=20)
    assert any("이전 성공 결과" in item.value for item in app.subheader)


def test_streamlit_successful_retry_replaces_previous_results(monkeypatch):
    from wlc_role_acl_collector import web_logic

    current = _successful_web_result("new-success")
    monkeypatch.setattr(web_logic, "run_web_collection", lambda *_args, **_kwargs: current)
    app = AppTest.from_file(str(APP_PATH))
    app.session_state["last_result"] = _successful_web_result("old-success")
    app.session_state["last_attempt_failed"] = True
    app.run(timeout=20)
    next(item for item in app.text_input if item.label == "WLC IP").set_value("192.0.2.10")
    next(item for item in app.text_input if item.label == "장비 ID").set_value("sample")
    next(item for item in app.text_input if item.label == "장비 PW").set_value("synthetic")
    app.button[0].click().run(timeout=20)

    assert not app.exception
    assert app.session_state["last_result"].run_id == "new-success"
    assert not any("이전 성공 결과" in item.value for item in app.subheader)
    assert not app.session_state["last_attempt_failed"]


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


def test_role_network_inclusion_starts_off_and_remains_the_submitted_selection(monkeypatch):
    from io import BytesIO

    import streamlit as st
    from wlc_role_acl_collector import web_logic

    uploaded = BytesIO(b"test")
    uploaded.name = "uploaded.xlsx"
    current = None
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: current)

    received = []

    def capture(request, **kwargs):
        received.append(request.export_local_role_networks)
        return _successful_web_result("captured")

    monkeypatch.setattr(web_logic, "run_web_collection", capture)
    app = AppTest.from_file(str(APP_PATH)).run(timeout=20)
    assert not app.checkbox[0].value
    next(item for item in app.text_input if item.label == "WLC IP").set_value("192.0.2.10")
    next(item for item in app.text_input if item.label == "장비 ID").set_value("test")
    next(item for item in app.text_input if item.label == "장비 PW").set_value("synthetic")
    current = uploaded
    app.button[0].click().run(timeout=20)
    app.checkbox[0].check()
    app.button[0].click().run(timeout=20)
    app.checkbox[0].uncheck()
    app.button[0].click().run(timeout=20)
    assert not app.exception
    assert received == [False, True, False]

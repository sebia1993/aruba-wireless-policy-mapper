from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).parents[1] / "portfolio_demo" / "app.py"


def _new_app() -> AppTest:
    app = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    assert not app.exception
    assert app.text_input(key="demo_host").value == "192.0.2.10"
    assert app.text_input(key="demo_username").disabled
    assert app.button(key="demo_run")
    return app


def test_portfolio_demo_runs_real_collection_and_report_pipeline():
    app = _new_app()

    app.selectbox(key="demo_scenario").set_value("success").run(timeout=10)
    app.button(key="demo_run").click().run(timeout=60)

    assert not app.exception
    assert any("정상 완료" in item.value for item in app.success)
    metric_labels = {item.label: item.value for item in app.metric}
    assert int(metric_labels["SSID"]) == 1
    assert int(metric_labels["Role"]) >= 1
    assert int(metric_labels["ACL Rule"]) >= 1

    result = app.session_state["demo_last_result"]
    assert result.success
    assert result.summary["collection_status"] == "completed"
    assert result.artifacts["html"].data
    assert result.artifacts["xlsx"].data
    assert result.artifacts["csv"].data
    assert len(result.preview_rows) == 2  # initial-role and mac-default-role
    assert {row["ssid"] for row in result.preview_rows} == {"GUEST-LAB"}
    workbook = load_workbook(BytesIO(result.artifacts["xlsx"].data), read_only=True)
    try:
        overview = list(workbook["Overview"].values)
        assert overview[1][overview[0].index("ssid_count")] == result.summary["ssid_count"] == 1
    finally:
        workbook.close()
    assert any("CONNECT OK" in line for line in app.session_state["demo_last_logs"])
    assert any("REPORT READY" in line for line in app.session_state["demo_last_logs"])


def test_portfolio_demo_partial_collection_is_reported_by_real_health_logic():
    app = _new_app()

    app.selectbox(key="demo_scenario").set_value("partial").run(timeout=10)
    app.button(key="demo_run").click().run(timeout=60)

    assert not app.exception
    result = app.session_state["demo_last_result"]
    assert result.success
    assert result.summary["collection_status"] == "partial"
    assert int(result.summary["failed_command_count"]) >= 1
    assert result.artifacts["html"].data
    assert any(
        "ERROR rights::guest-logon" in line
        for line in app.session_state["demo_last_logs"]
    )


def test_portfolio_demo_auth_failure_uses_real_collector_failure_path():
    app = _new_app()

    app.selectbox(key="demo_scenario").set_value("auth_failed").run(timeout=10)
    app.button(key="demo_run").click().run(timeout=60)

    assert not app.exception
    result = app.session_state["demo_last_result"]
    assert not result.success
    assert result.summary["collection_status"] == "failed"
    assert result.summary["failure_stage"]
    assert any("RUN FAILED" in line for line in app.session_state["demo_last_logs"])


def test_guided_result_rerun_preserves_report_and_run_identity():
    app = _new_app()
    app.button(key="demo_run").click().run(timeout=60)
    assert not app.exception
    token = app.session_state.guided_run_id
    result = app.session_state.demo_last_result
    assert any('data-phase="result"' in h.proto.body for h in app.get("html"))
    app.run()
    assert app.session_state.guided_run_id == token
    assert app.session_state.demo_last_result is result
    assert app.session_state.guide_events


def test_missing_configuration_shows_failure_in_guided_view():
    app = _new_app()
    app.selectbox(key="demo_scenario").set_value("missing_config").run()
    app.button(key="demo_run").click().run(timeout=60)
    assert not app.exception
    assert not app.session_state.demo_last_result.success
    assert any('data-phase="error"' in h.proto.body for h in app.get("html"))

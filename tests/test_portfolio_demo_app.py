from pathlib import Path

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
    assert any("보고서 생성이 완료되었습니다." in item.value for item in app.success)
    metric_labels = {item.label: item.value for item in app.metric}
    assert int(metric_labels["SSID"]) >= 1
    assert int(metric_labels["Role"]) >= 1
    assert int(metric_labels["ACL Rule"]) >= 1

    result = app.session_state["demo_last_result"]
    assert result.success
    assert result.summary["collection_status"] == "complete"
    assert result.artifacts["html"].data
    assert result.artifacts["xlsx"].data
    assert result.artifacts["csv"].data
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
    assert any("ERROR rights::guest-logon" in line for line in app.session_state["demo_last_logs"])


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

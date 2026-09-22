from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).parents[1] / "portfolio_demo" / "app.py"


def test_portfolio_demo_runs_real_offline_collection_pipeline():
    app = AppTest.from_file(str(APP_PATH)).run(timeout=30)

    assert not app.exception
    assert app.text_input(key="demo_host").value == "192.0.2.10"
    assert app.text_input(key="demo_username").disabled
    assert app.button(key="demo_run")

    app.button(key="demo_run").click().run(timeout=60)

    assert not app.exception
    assert any("Demo 수집과 보고서 생성이 완료되었습니다." in item.value for item in app.success)
    metric_labels = {item.label: item.value for item in app.metric}
    assert int(metric_labels["SSID"]) >= 1
    assert int(metric_labels["Role"]) >= 1
    assert int(metric_labels["ACL Rule"]) >= 1
    assert "demo_last_result" in app.session_state
    result = app.session_state["demo_last_result"]
    assert result.success
    assert result.artifacts["html"].data
    assert result.artifacts["xlsx"].data
    assert result.artifacts["csv"].data

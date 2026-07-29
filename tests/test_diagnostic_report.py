import json

import pytest

import wlc_role_acl_collector.diagnostic_report as diagnostic_report
from wlc_role_acl_collector.diagnostic_events import DiagnosticEvent, event_from_code
from wlc_role_acl_collector.diagnostic_report import write_diagnostic_report


def test_diagnostic_report_writes_no_raw_output_and_redacts_sensitive_metadata(tmp_path):
    paths = write_diagnostic_report(
        tmp_path,
        events=[
            DiagnosticEvent(
                stage="DGN-NET",
                status="error",
                code="WLC-NET-001",
                command_id="rights::finance-employee",
                message="Connection timeout",
                detail="10.10.10.10 password Secret123 wlc-prod-01 show rights finance-employee",
            ),
            event_from_code("WLC-NET-001", command_id="connect"),
        ],
        primary_code="WLC-NET-001",
        metadata={"host": "10.10.10.10", "hostname": "wlc-prod-01", "password": "Secret123"},
    )

    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    status = json.loads(paths["status"].read_text(encoding="utf-8"))
    html = paths["html"].read_text(encoding="utf-8")
    log = paths["log"].read_text(encoding="utf-8")

    assert payload["raw_output_saved"] is False
    assert payload["primary"]["code"] == "WLC-NET-001"
    assert status["status"] == "completed"
    for text in (paths["json"].read_text(encoding="utf-8"), html, log):
        assert "10.10.10.10" not in text
        assert "Secret123" not in text
        assert "wlc-prod-01" not in text
        assert "finance-employee" not in text


def test_diagnostic_report_failure_keeps_previous_files_and_marks_failed(monkeypatch, tmp_path):
    json_path = tmp_path / "diagnostic_summary.json"
    html_path = tmp_path / "diagnostic_summary.html"
    log_path = tmp_path / "diagnostic_run.log"
    json_path.write_text("old-json", encoding="utf-8")
    html_path.write_text("old-html", encoding="utf-8")
    log_path.write_text("old-log", encoding="utf-8")
    original_write = diagnostic_report.atomic_write_text

    def fail_html_staging(path, value, **kwargs):
        if ".staging.html" in path.name:
            raise OSError("disk full")
        return original_write(path, value, **kwargs)

    monkeypatch.setattr(diagnostic_report, "atomic_write_text", fail_html_staging)

    with pytest.raises(OSError, match="disk full"):
        write_diagnostic_report(
            tmp_path,
            events=[event_from_code("WLC-NET-001", command_id="connect")],
            primary_code="WLC-NET-001",
        )

    status = json.loads((tmp_path / "diagnostic_status.json").read_text(encoding="utf-8"))
    assert status["status"] == "failed"
    assert status["error_type"] == "OSError"
    assert json_path.read_text(encoding="utf-8") == "old-json"
    assert html_path.read_text(encoding="utf-8") == "old-html"
    assert log_path.read_text(encoding="utf-8") == "old-log"
    assert not list(tmp_path.glob(".*.staging.*"))
    assert not list(tmp_path.glob(".*.backup.*"))

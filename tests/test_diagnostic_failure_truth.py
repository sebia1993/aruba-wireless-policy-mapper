"""Final collector evidence must control safe diagnostic outcomes."""

import json
from pathlib import Path

import pytest

import wlc_role_acl_collector.cli as cli
import wlc_role_acl_collector.diagnostic_mode as diagnostic_mode
from wlc_role_acl_collector.collector import collect_from_offline_raw
from wlc_role_acl_collector.models import CollectionResult, CommandOutput, Controller, ControllerTarget


@pytest.mark.parametrize("callback_count", [0, 2], ids=["no-callback", "duplicate-callbacks"])
@pytest.mark.parametrize(
    "command_id,error,expected_code",
    [
        ("rights::finance-employee", "role details unavailable", "WLC-CMD-004"),
        ("netdestination::payroll-servers", "alias details unavailable", "WLC-CMD-004"),
        ("user_table", "command timed out", "WLC-CMD-002"),
        ("disconnect", "session close failed", "WLC-UNK-001"),
        ("disconnect", "", "WLC-UNK-001"),
    ],
)
def test_final_optional_failure_controls_diagnostic_and_cli(
    monkeypatch, tmp_path, callback_count, command_id, error, expected_code
):
    # Ignoring final failures or trusting callback counts would incorrectly report OK.
    target = ControllerTarget(Controller(name="sample_controller", host="192.0.2.10"))
    collection = collect_from_offline_raw(target.controller, Path(__file__).parent / "fixtures")
    collection.commands = [item for item in collection.commands if item.command_id != command_id]
    collection.commands.append(CommandOutput(command_id, command_id, success=False, error=error))

    def synthetic_collection(controller, *, progress_callback, **kwargs):
        for _ in range(callback_count):
            progress_callback("command_error", {"command_id": command_id, "error": error})
        return collection

    monkeypatch.setattr(diagnostic_mode, "collect_from_controller", synthetic_collection)
    run = diagnostic_mode.run_diagnostic(target, output_root=tmp_path / "direct")

    assert run.primary_code == expected_code
    failures = [event for event in run.events if event.status == "error" and event.command_id == command_id]
    assert len(failures) == 1
    assert failures[0].code == expected_code
    payload = json.loads(run.report_paths["json"].read_text(encoding="utf-8"))
    assert payload["status"] == "attention"
    assert payload["primary"]["code"] == expected_code
    assert json.loads(run.report_paths["status"].read_text(encoding="utf-8"))["status"] == "completed"
    assert all(run.report_paths[k].is_file() for k in ("json", "html", "log"))
    assert not (run.run_dir / "raw").exists()

    monkeypatch.setattr(cli, "_resolve_targets", lambda args: [target])
    assert cli.main(["diagnose", "--output-dir", str(tmp_path / "cli")]) == 1
    cli_payload = json.loads(next((tmp_path / "cli").glob("*/diagnostic_summary.json")).read_text())
    assert cli_payload["primary"]["code"] == expected_code


@pytest.mark.parametrize(
    "required,error,expected_code",
    [
        (CommandOutput("configuration_effective", "show configuration effective", success=False, error="permission denied"), None, "WLC-CMD-003"),
        (CommandOutput("configuration_effective", "show configuration effective", output='user-role "synthetic-role"\n!\n', error="permission denied"), None, "WLC-CMD-003"),
        (CommandOutput("configuration_effective", "show configuration effective", output="permission denied", error="permission denied"), None, "WLC-CMD-003"),
        (CommandOutput("configuration_effective", "show configuration effective", success=False, error="output unavailable"), None, "WLC-CMD-001"),
        (CommandOutput("configuration_effective", "show configuration effective", output=""), None, "WLC-CMD-001"),
        (CommandOutput("configuration_effective", "show configuration effective", output="configuration"), ValueError("unsupported output"), "WLC-PRS-001"),
    ],
)
def test_required_and_parse_failures_take_precedence_over_optional_failure(
    monkeypatch, tmp_path, required, error, expected_code
):
    target = ControllerTarget(Controller(name="synthetic", host="192.0.2.10"))
    collection = CollectionResult(target.controller, commands=[
        CommandOutput("user_table", "show user-table", success=False, error="command timed out"),
        required,
    ])
    monkeypatch.setattr(diagnostic_mode, "collect_from_controller", lambda *a, **kw: collection)
    if error:
        def fail_parse(results):
            raise error
        monkeypatch.setattr(diagnostic_mode, "build_parsed_controllers", fail_parse)

    run = diagnostic_mode.run_diagnostic(target, output_root=tmp_path)

    assert run.primary_code == expected_code
    required_events = [event for event in run.events if event.command_id == "configuration_effective" and event.status == "error"]
    assert len(required_events) == (0 if error else 1)
    if required_events:
        assert required_events[0].code == expected_code


@pytest.mark.parametrize("command_id,error", [
    ("rights::finance-employee", "role details unavailable"),
    ("user_table", "command timed out"),
    ("disconnect", "session close failed"),
])
def test_cli_diagnose_returns_failure_for_final_optional_failure(monkeypatch, tmp_path, command_id, error):
    # CLI must consume the actual diagnostic outcome rather than claim success.
    target = ControllerTarget(Controller(name="sample_controller", host="192.0.2.10"))
    collection = collect_from_offline_raw(target.controller, Path(__file__).parent / "fixtures")
    collection.commands.append(CommandOutput(command_id, command_id, success=False, error=error))
    monkeypatch.setattr(diagnostic_mode, "collect_from_controller", lambda *a, **kw: collection)
    monkeypatch.setattr(cli, "_resolve_targets", lambda args: [target])

    assert cli.main(["diagnose", "--output-dir", str(tmp_path)]) == 1
    assert next(tmp_path.glob("*/diagnostic_summary.html")).is_file()


def test_parse_warning_preserves_successful_diagnostic_outcome(monkeypatch, tmp_path):
    target = ControllerTarget(Controller(name="synthetic", host="192.0.2.10"))
    collection = CollectionResult(target.controller, commands=[CommandOutput(
        "configuration_effective", "show configuration effective",
        output='user-role "synthetic-role"\n access-list session missing-acl\n!\n',
    )])
    monkeypatch.setattr(diagnostic_mode, "collect_from_controller", lambda *a, **kw: collection)

    run = diagnostic_mode.run_diagnostic(target, output_root=tmp_path)

    assert run.primary_code == "OK"
    assert any(event.code == "WLC-PRS-002" and event.status == "warning" for event in run.events)
    assert json.loads(run.report_paths["json"].read_text())["status"] == "ok"


def test_duration_failure_deduplicates_callback_and_final_evidence(monkeypatch, tmp_path):
    target = ControllerTarget(Controller(name="synthetic", host="192.0.2.10"))
    collection = CollectionResult(target.controller, commands=[
        CommandOutput("duration_limit", "collection duration limit", success=False, error="duration exceeded"),
        CommandOutput("disconnect", "disconnect", success=False, error="session close failed"),
    ])

    def synthetic_collection(controller, *, progress_callback, **kwargs):
        for _ in range(2):
            progress_callback("command_error", {"command_id": "duration_limit", "error": "duration exceeded"})
        return collection

    monkeypatch.setattr(diagnostic_mode, "collect_from_controller", synthetic_collection)
    run = diagnostic_mode.run_diagnostic(target, output_root=tmp_path)

    assert run.primary_code == "WLC-CMD-002"
    assert len([event for event in run.events if event.command_id == "duration_limit" and event.status == "error"]) == 1
    assert any(event.command_id == "disconnect" and event.status == "error" for event in run.events)

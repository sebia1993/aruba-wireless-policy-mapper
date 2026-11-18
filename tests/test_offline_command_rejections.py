"""Offline raw input must retain the same failure truth as live collection."""

from pathlib import Path
import shutil

import pytest

from wlc_role_acl_collector.collection_health import assess_collection_results
from wlc_role_acl_collector.collector import collect_from_offline_raw
from wlc_role_acl_collector.diagnostic_mode import run_diagnostic
from wlc_role_acl_collector.models import Controller, ControllerTarget
from wlc_role_acl_collector.report import build_parsed_controllers


RAW_FILES = (
    ("configuration_effective", "show_configuration_effective.txt", "failed"),
    ("ip_interface_brief", "show_ip_interface_brief.txt", "partial"),
    ("user_table", "show_user_table.txt", "partial"),
    ("rights::corp-employee", "show_rights__corp-employee.txt", "partial"),
    ("netdestination::controller", "show_netdestination__controller.txt", "partial"),
)
REJECTION = "% Permission denied\n"


@pytest.fixture
def offline_input(tmp_path):
    raw_root = tmp_path / "input"
    shutil.copytree(Path(__file__).parent / "fixtures" / "sample_controller", raw_root / "sample_controller")
    target = ControllerTarget(Controller(name="sample_controller", host="192.0.2.10"))
    return raw_root, target


@pytest.mark.parametrize("command_id,filename,status", RAW_FILES)
def test_offline_rejection_retains_evidence_and_reaches_health_and_diagnostic(
    offline_input, tmp_path, command_id, filename, status,
):
    raw_root, target = offline_input
    (raw_root / target.controller.name / filename).write_text(REJECTION, encoding="utf-8")

    result = collect_from_offline_raw(target.controller, raw_root)
    health = assess_collection_results([result])
    parsed = build_parsed_controllers([result])
    diagnostic = run_diagnostic(target, output_root=tmp_path / "diagnostic", offline_raw_dir=raw_root)

    command = next(item for item in result.commands if item.command_id == command_id)
    assert health.status == status
    assert health.failed_command_ids == (command_id,)
    assert command.success is False
    assert command.error == REJECTION.strip()
    assert command.output == REJECTION
    assert result.command_output(command_id) == ""
    if status == "partial":
        assert result.command_output("configuration_effective")
        assert parsed[0].ssid_role_mappings
        assert parsed[0].role_policies
    else:
        assert not parsed[0].ssid_role_mappings
    assert diagnostic.primary_code == "WLC-CMD-003"
    errors = [event for event in diagnostic.events if event.status == "error"]
    assert [(event.command_id, event.code) for event in errors] == [(command_id, "WLC-CMD-003")]


def test_offline_ordinary_descriptions_remain_completed_and_diagnostic_ok(offline_input, tmp_path):
    raw_root, target = offline_input
    description = '\ndescription "error: permission denied, invalid input, not authorized"\n'
    for _command_id, filename, _status in RAW_FILES:
        path = raw_root / target.controller.name / filename
        with path.open("a", encoding="utf-8") as raw_file:
            raw_file.write(description)

    result = collect_from_offline_raw(target.controller, raw_root)
    diagnostic = run_diagnostic(target, output_root=tmp_path / "diagnostic", offline_raw_dir=raw_root)

    assert assess_collection_results([result]).status == "completed"
    assert all(command.success and not command.error for command in result.commands)
    assert build_parsed_controllers([result])[0].ssid_role_mappings
    assert diagnostic.primary_code == "OK"
    assert not [event for event in diagnostic.events if event.status == "error"]


def test_offline_missing_required_file_keeps_existing_failure(offline_input):
    raw_root, target = offline_input
    missing = raw_root / target.controller.name / "show_configuration_effective.txt"
    missing.unlink()

    result = collect_from_offline_raw(target.controller, raw_root)

    assert len(result.commands) == 1
    assert result.commands[0].success is False
    assert result.commands[0].error == f"missing offline raw file: {missing}"
    assert result.commands[0].output == ""
    assert assess_collection_results([result]).status == "failed"


def test_offline_missing_optional_files_remain_omitted(offline_input):
    raw_root, target = offline_input
    for path in (raw_root / target.controller.name).iterdir():
        if path.name != "show_configuration_effective.txt":
            path.unlink()

    result = collect_from_offline_raw(target.controller, raw_root)

    assert [command.command_id for command in result.commands] == ["configuration_effective"]
    assert assess_collection_results([result]).status == "completed"

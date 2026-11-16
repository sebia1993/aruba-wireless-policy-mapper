"""Collector response signatures and diagnostic outcomes must agree."""

from pathlib import Path

import pytest

from wlc_role_acl_collector import diagnostic_mode
from wlc_role_acl_collector.collector import collect_from_offline_raw
from wlc_role_acl_collector.models import Controller, ControllerTarget


def _fixture():
    target = ControllerTarget(Controller(name="sample_controller", host="192.0.2.10"))
    result = collect_from_offline_raw(target.controller, Path(__file__).parent / "fixtures")
    configuration = next(item for item in result.commands if item.command_id == "configuration_effective")
    return target, result, configuration


@pytest.mark.parametrize("description", ["permission denied", "invalid input", "not authorized"])
def test_diagnostic_keeps_successful_policy_descriptions(description, monkeypatch, tmp_path):
    target, result, configuration = _fixture()
    configuration.output += f'\ndescription "{description}"\n'
    monkeypatch.setattr(diagnostic_mode, "collect_from_controller", lambda *args, **kwargs: result)

    run = diagnostic_mode.run_diagnostic(target, output_root=tmp_path)

    assert run.primary_code == "OK"
    assert not [event for event in run.events if event.status == "error"]


@pytest.mark.parametrize("rejection", [
    "Error:You do not have permission to execute this command",
    "% Unknown command: show configuration effective",
    "% Not authorized to execute this command",
])
@pytest.mark.parametrize("failed_record", [False, True])
def test_diagnostic_recognizes_rejections_in_raw_and_failed_records(rejection, failed_record, monkeypatch, tmp_path):
    target, result, configuration = _fixture()
    configuration.output = rejection
    configuration.success = not failed_record
    configuration.error = rejection if failed_record else ""
    monkeypatch.setattr(diagnostic_mode, "collect_from_controller", lambda *args, **kwargs: result)

    run = diagnostic_mode.run_diagnostic(target, output_root=tmp_path)

    assert run.primary_code == "WLC-CMD-003"
    errors = [event for event in run.events if event.command_id == "configuration_effective" and event.status == "error"]
    assert len(errors) == 1
    assert errors[0].code == "WLC-CMD-003"

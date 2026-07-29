from pathlib import Path

from openpyxl import Workbook, load_workbook

import wlc_role_acl_collector.cli as cli
from wlc_role_acl_collector.cli import main
from wlc_role_acl_collector.interactive import prompt_controller_targets
from wlc_role_acl_collector.models import (
    CollectionResult,
    CommandOutput,
    Controller,
    ControllerCredentials,
    ControllerTarget,
)


def test_cli_collect_offline(tmp_path):
    controllers = tmp_path / "controllers.csv"
    controllers.write_text(
        "name,host,protocol,port,device_type,username_env,password_env,enable_password_env\n"
        "sample_controller,192.0.2.10,ssh,22,aruba_os,,,\n",
        encoding="utf-8",
    )
    fixture_root = Path(__file__).parent / "fixtures"
    role_networks = tmp_path / "role_networks.xlsx"
    _write_role_networks(role_networks)

    exit_code = main(
        [
            "collect",
            "--controllers",
            str(controllers),
            "--offline-raw-dir",
            str(fixture_root),
            "--output-dir",
            str(tmp_path / "outputs"),
            "--role-networks",
            str(role_networks),
        ]
    )

    assert exit_code == 0
    reports = list((tmp_path / "outputs").glob("*/ssid_role_acl_report.xlsx"))
    assert len(reports) == 1
    workbook = load_workbook(reports[0], read_only=True)
    assert "Local_Role_Networks" not in workbook.sheetnames


def test_cli_can_explicitly_export_local_role_networks(tmp_path):
    controllers = tmp_path / "controllers.csv"
    controllers.write_text(
        "name,host,protocol,port,device_type,username_env,password_env,enable_password_env\n"
        "sample_controller,192.0.2.10,ssh,22,aruba_os,,,\n",
        encoding="utf-8",
    )
    fixture_root = Path(__file__).parent / "fixtures"
    role_networks = tmp_path / "role_networks.xlsx"
    _write_role_networks(role_networks)

    exit_code = main(
        [
            "collect",
            "--controllers",
            str(controllers),
            "--offline-raw-dir",
            str(fixture_root),
            "--output-dir",
            str(tmp_path / "outputs"),
            "--role-networks",
            str(role_networks),
            "--export-local-role-networks",
        ]
    )

    assert exit_code == 0
    reports = list((tmp_path / "outputs").glob("*/ssid_role_acl_report.xlsx"))
    assert len(reports) == 1
    workbook = load_workbook(reports[0], read_only=True)
    assert "Local_Role_Networks" in workbook.sheetnames


def test_cli_interactive_defaults_to_ssh(monkeypatch, tmp_path):
    prompts = iter(
        [
            "10.10.10.10",
            "",
            "",
            "",
            "admin",
            "",
        ]
    )
    captured = {}

    monkeypatch.setattr(
        cli,
        "prompt_controller_targets",
        lambda: prompt_controller_targets(
            input_func=lambda _prompt: next(prompts),
            password_func=lambda _prompt: "secret",
        ),
    )

    def fake_collect(controller, *, timeout, credentials):
        captured["controller"] = controller
        captured["credentials"] = credentials
        return CollectionResult(
            controller=controller,
            commands=[
                CommandOutput(
                    command_id="configuration_effective",
                    command="show configuration effective",
                    output="show configuration effective\n",
                )
            ],
        )

    monkeypatch.setattr(cli, "collect_from_controller", fake_collect)

    exit_code = main(["collect", "--output-dir", str(tmp_path / "outputs")])

    assert exit_code == 0
    assert captured["controller"].host == "10.10.10.10"
    assert captured["controller"].name == "wlc-10.10.10.10"
    assert captured["controller"].protocol == "ssh"
    assert captured["controller"].port == 22
    assert captured["controller"].device_type == "aruba_os"
    assert captured["credentials"].username == "admin"


def test_cli_returns_failure_when_required_configuration_was_not_collected(monkeypatch, tmp_path, capsys):
    controller = Controller(name="failed-wlc", host="192.0.2.10")
    target = ControllerTarget(
        controller=controller,
        credentials=ControllerCredentials(username="admin", password="secret"),
    )
    monkeypatch.setattr(cli, "_resolve_targets", lambda _args: [target])
    monkeypatch.setattr(
        cli,
        "collect_from_controller",
        lambda *_args, **_kwargs: CollectionResult(
            controller=controller,
            commands=[
                CommandOutput(
                    command_id="connect",
                    command="connect",
                    success=False,
                    error="authentication failed",
                )
            ],
        ),
    )

    exit_code = main(["collect", "--output-dir", str(tmp_path / "outputs")])

    assert exit_code == cli.COLLECT_EXIT_FAILED
    assert "failed-wlc" in capsys.readouterr().err


def test_cli_returns_partial_when_optional_command_failed(monkeypatch, tmp_path, capsys):
    controller = Controller(name="partial-wlc", host="192.0.2.10")
    target = ControllerTarget(
        controller=controller,
        credentials=ControllerCredentials(username="admin", password="secret"),
    )
    monkeypatch.setattr(cli, "_resolve_targets", lambda _args: [target])
    monkeypatch.setattr(
        cli,
        "collect_from_controller",
        lambda *_args, **_kwargs: CollectionResult(
            controller=controller,
            commands=[
                CommandOutput(
                    command_id="configuration_effective",
                    command="show configuration effective",
                    output="show configuration effective\n",
                ),
                CommandOutput(
                    command_id="user_table",
                    command="show user-table",
                    success=False,
                    error="command timed out",
                ),
            ],
        ),
    )

    exit_code = main(["collect", "--output-dir", str(tmp_path / "outputs")])

    assert exit_code == cli.COLLECT_EXIT_PARTIAL
    assert "partial-wlc:user_table" in capsys.readouterr().err


def test_cli_rejects_timeout_outside_supported_range(capsys):
    exit_code = main(["collect", "--timeout", "1"])

    assert exit_code == cli.COLLECT_EXIT_INPUT_ERROR
    assert "5에서 600" in capsys.readouterr().err


def _write_role_networks(path: Path) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["role", "network", "subnet_mask"])
    worksheet.append(["guest-logon", "10.30.0.0", "255.255.255.0"])
    workbook.save(path)

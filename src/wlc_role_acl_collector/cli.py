from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .collector import collect_from_controller, collect_from_offline_raw
from .collection_health import (
    COLLECTION_FAILED,
    COLLECTION_PARTIAL,
    assess_collection_results,
)
from .config import load_controllers
from .diagnostic_mode import run_diagnostic
from .diagnostics import FailureInfo, classify_error_message
from .hostkeys import trust_host_key_interactive
from .interactive import prompt_controller_targets
from .mock_server import run_mock_server
from .models import CollectionResult, CommandOutput, ControllerTarget
from .report import build_parsed_controllers, create_run_dir, write_raw_result, write_reports
from .role_networks import RoleNetworkDefinitionError, load_role_network_definitions
from .validation import validate_port, validate_timeout_seconds, validate_wlc_address


COLLECT_EXIT_OK = 0
COLLECT_EXIT_FAILED = 1
COLLECT_EXIT_INPUT_ERROR = 2
COLLECT_EXIT_PARTIAL = 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wlc-role-acl-collector",
        description="Collect Aruba AOS8 WLC SSID, Role, and ACL mappings.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect", help="Collect data and generate reports")
    collect_parser.add_argument("--controllers", type=Path, help="controllers CSV path")
    collect_parser.add_argument("--output-dir", default=Path("outputs"), type=Path, help="report output root")
    collect_parser.add_argument("--timeout", default=60, type=int, help="per-command timeout seconds")
    collect_parser.add_argument(
        "--role-networks",
        type=Path,
        default=None,
        help="optional local Role network mapping Excel file; not exported unless explicitly enabled",
    )
    collect_parser.add_argument(
        "--export-local-role-networks",
        action="store_true",
        help="include local Role network mapping data in generated reports",
    )
    collect_parser.add_argument(
        "--offline-raw-dir",
        type=Path,
        default=None,
        help="read raw command outputs from a fixture directory instead of connecting to WLCs",
    )

    diagnose_parser = subparsers.add_parser("diagnose", help="Run field diagnostics without saving raw output")
    diagnose_parser.add_argument("--controllers", type=Path, help="controllers CSV path")
    diagnose_parser.add_argument("--output-dir", default=Path("outputs"), type=Path, help="diagnostic output root")
    diagnose_parser.add_argument("--timeout", default=60, type=int, help="per-command timeout seconds")
    diagnose_parser.add_argument(
        "--offline-raw-dir",
        type=Path,
        default=None,
        help="read offline raw fixture data for local diagnostic testing",
    )

    mock_parser = subparsers.add_parser("mock-server", help="Start a local synthetic WLC SSH/Telnet mock server")
    mock_parser.add_argument("--protocol", choices=("ssh", "telnet"), default="telnet")
    mock_parser.add_argument(
        "--scenario",
        type=Path,
        default=Path("config/mock_scenarios/success_minimal.json"),
        help="mock scenario JSON file",
    )
    mock_parser.add_argument("--host", default="127.0.0.1", help="local listen address")
    mock_parser.add_argument("--port", type=int, default=0, help="local listen port; 0 selects a free port")

    trust_parser = subparsers.add_parser(
        "trust-host-key",
        help="Review and pin one SSH server key before entering device credentials",
    )
    trust_parser.add_argument("--host", required=True, help="WLC IP or hostname")
    trust_parser.add_argument("--port", type=int, default=22, help="SSH port")
    trust_parser.add_argument("--timeout", type=float, default=15.0, help="server-key probe timeout seconds")

    args = parser.parse_args(argv)
    if args.command == "collect":
        return _collect(args)
    if args.command == "diagnose":
        return _diagnose(args)
    if args.command == "mock-server":
        run_mock_server(args.protocol, args.scenario, host=args.host, port=args.port)
        return 0
    if args.command == "trust-host-key":
        return _trust_host_key(args)
    return 2


def _trust_host_key(args: argparse.Namespace) -> int:
    try:
        host = validate_wlc_address(args.host)
        port = validate_port(args.port)
        timeout = float(args.timeout)
        if not 1.0 <= timeout <= 60.0:
            raise ValueError("서버 키 확인 Timeout은 1초에서 60초 사이여야 합니다.")
        trust_host_key_interactive(host, port, timeout=timeout)
    except (OSError, RuntimeError, PermissionError, ValueError) as exc:
        print(f"SSH 서버 키 승인 실패: {exc}", file=sys.stderr)
        return COLLECT_EXIT_INPUT_ERROR
    return COLLECT_EXIT_OK


def _collect(args: argparse.Namespace) -> int:
    try:
        timeout = validate_timeout_seconds(args.timeout)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return COLLECT_EXIT_INPUT_ERROR
    try:
        local_role_networks = load_role_network_definitions(args.role_networks) if args.role_networks else []
    except RoleNetworkDefinitionError as exc:
        print(f"Role network Excel error: {exc}", file=sys.stderr)
        return COLLECT_EXIT_INPUT_ERROR

    try:
        targets = _resolve_targets(args)
    except (OSError, ValueError, EOFError) as exc:
        print(f"WLC 대상 설정 오류: {exc}", file=sys.stderr)
        return COLLECT_EXIT_INPUT_ERROR
    if not targets:
        print("No WLC targets were provided.", file=sys.stderr)
        return COLLECT_EXIT_INPUT_ERROR

    try:
        run_dir = create_run_dir(args.output_dir)
    except (OSError, RuntimeError) as exc:
        _print_failure(
            _local_failure(
                code="WLC-RPT-001",
                title="결과 폴더를 만들지 못했습니다",
                detail=str(exc),
                suggestion="쓰기 가능한 로컬 폴더를 --output-dir로 지정하고 다시 실행하세요.",
            )
        )
        return COLLECT_EXIT_FAILED
    raw_dir = run_dir / "raw"

    results: list[CollectionResult] = []
    runtime_failure_count = 0
    for target in targets:
        controller = target.controller
        try:
            if args.offline_raw_dir:
                result = collect_from_offline_raw(controller, args.offline_raw_dir)
            else:
                result = collect_from_controller(
                    controller,
                    timeout=timeout,
                    credentials=target.credentials,
                )
        except Exception as exc:
            runtime_failure_count += 1
            failure = classify_error_message(str(exc))
            print(f"[{controller.name}] {failure.as_text()}", file=sys.stderr)
            result = CollectionResult(
                controller=controller,
                commands=[
                    CommandOutput(
                        command_id="collection_runtime",
                        command="collection runtime",
                        success=False,
                        error=str(exc),
                    )
                ],
            )
        try:
            write_raw_result(result, raw_dir)
        except OSError as exc:
            _print_failure(
                _local_failure(
                    code="WLC-RPT-001",
                    title="수집 원본 파일을 저장하지 못했습니다",
                    detail=str(exc),
                    suggestion="출력 폴더 권한, 디스크 여유 공간, 파일 잠금 상태를 확인하세요.",
                ),
                prefix=f"[{controller.name}] ",
            )
            return COLLECT_EXIT_FAILED
        results.append(result)

    parsed = []
    for result in results:
        try:
            parsed.extend(build_parsed_controllers([result]))
        except Exception as exc:
            runtime_failure_count += 1
            failure = _local_failure(
                code="WLC-PRS-001",
                title="수집한 WLC 설정을 해석하지 못했습니다",
                detail=str(exc),
                suggestion="대상이 Aruba AOS8 WLC인지 확인하고 안전 진단 결과를 검토하세요.",
            )
            print(f"[{result.controller.name}] {failure.as_text()}", file=sys.stderr)
            result.commands.append(
                CommandOutput(
                    command_id="parse_runtime",
                    command="parse collected configuration",
                    success=False,
                    error=str(exc),
                )
            )
            try:
                write_raw_result(result, raw_dir)
            except OSError as raw_exc:
                _print_failure(
                    _local_failure(
                        code="WLC-RPT-001",
                        title="파싱 실패 상태를 원본 파일에 기록하지 못했습니다",
                        detail=str(raw_exc),
                        suggestion="출력 폴더 권한과 파일 잠금 상태를 확인하세요.",
                    ),
                    prefix=f"[{result.controller.name}] ",
                )
                return COLLECT_EXIT_FAILED

    try:
        files = write_reports(
            parsed_controllers=parsed,
            collection_results=results,
            output_dir=run_dir,
            local_role_networks=local_role_networks,
            export_local_role_networks=args.export_local_role_networks,
            access_history_enabled=False,
        )
    except Exception as exc:
        _print_failure(
            _local_failure(
                code="WLC-RPT-002",
                title="HTML/Excel 보고서를 생성하지 못했습니다",
                detail=str(exc),
                suggestion="report_status.json, 출력 폴더 권한, 디스크 여유 공간을 확인하세요.",
            )
        )
        return COLLECT_EXIT_FAILED

    print(f"Output directory: {run_dir}")
    if local_role_networks and not args.export_local_role_networks:
        print("Role network Excel was loaded for this run only; local networks were not exported.")
    print(f"Excel: {files['xlsx']}")
    print(f"HTML: {files['html']}")
    exit_code = _collection_exit_code(results)
    if runtime_failure_count:
        exit_code = COLLECT_EXIT_FAILED

    if exit_code == COLLECT_EXIT_FAILED:
        failed_controllers = [
            result.controller.name
            for result in results
            if not result.command_output("configuration_effective")
            or any(command.command_id == "parse_runtime" for command in result.commands)
        ]
        print(
            "Collection failed for required WLC data: " + ", ".join(failed_controllers),
            file=sys.stderr,
        )
    elif exit_code == COLLECT_EXIT_PARTIAL:
        failed_commands = [
            f"{result.controller.name}:{command.command_id}"
            for result in results
            for command in result.commands
            if not command.success
        ]
        print(
            "Collection completed with failed optional commands: " + ", ".join(failed_commands),
            file=sys.stderr,
        )
    return exit_code


def _collection_exit_code(results: list[CollectionResult]) -> int:
    health = assess_collection_results(results)
    if health.status == COLLECTION_FAILED:
        return COLLECT_EXIT_FAILED
    if health.status == COLLECTION_PARTIAL:
        return COLLECT_EXIT_PARTIAL
    return COLLECT_EXIT_OK


def _resolve_targets(args: argparse.Namespace) -> list[ControllerTarget]:
    if args.controllers:
        return [ControllerTarget(controller=controller) for controller in load_controllers(args.controllers)]
    return prompt_controller_targets()


def _diagnose(args: argparse.Namespace) -> int:
    try:
        timeout = validate_timeout_seconds(args.timeout)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return COLLECT_EXIT_INPUT_ERROR
    try:
        targets = _resolve_targets(args)
    except (OSError, ValueError, EOFError) as exc:
        print(f"WLC 대상 설정 오류: {exc}", file=sys.stderr)
        return COLLECT_EXIT_INPUT_ERROR
    if not targets:
        print("No WLC targets were provided.", file=sys.stderr)
        return COLLECT_EXIT_INPUT_ERROR

    exit_code = 0
    for target in targets:
        try:
            diagnostic = run_diagnostic(
                target,
                output_root=args.output_dir,
                timeout=timeout,
                offline_raw_dir=args.offline_raw_dir,
            )
        except Exception as exc:
            failure = classify_error_message(str(exc))
            print(f"[{target.controller.name}] {failure.as_text()}", file=sys.stderr)
            exit_code = COLLECT_EXIT_FAILED
            continue
        print(f"Diagnostic output directory: {diagnostic.run_dir}")
        print(f"Primary code: {diagnostic.primary_code}")
        print(f"Diagnostic JSON: {diagnostic.report_paths['json']}")
        print(f"Diagnostic HTML: {diagnostic.report_paths['html']}")
        if diagnostic.primary_code != "OK":
            exit_code = 1
    return exit_code


def _local_failure(*, code: str, title: str, detail: str, suggestion: str) -> FailureInfo:
    return FailureInfo(
        category="local_runtime",
        title=title,
        detail=detail,
        suggestion=suggestion,
        code=code,
    )


def _print_failure(failure: FailureInfo, *, prefix: str = "") -> None:
    print(f"{prefix}{failure.as_text()}", file=sys.stderr)

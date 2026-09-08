"""Capture current CustomTkinter widgets and actual offline fixture summary."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from capture_windows import (
    block_network,
    capture_window,
    prepare_capture_desktop,
    write_manifest,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    prepare_capture_desktop()
    block_network()
    from wlc_role_acl_collector import gui_app as gui
    from wlc_role_acl_collector.collector import collect_from_offline_raw
    from wlc_role_acl_collector.models import Controller
    from wlc_role_acl_collector.report import build_parsed_controllers, write_reports

    root = Path(__file__).resolve().parents[1]
    # Capture a supported resized window without the runner monitor clipping its height.
    gui._window_work_area = lambda _handle: None
    with tempfile.TemporaryDirectory(prefix="mapper-docs-") as directory:
        gui.default_gui_output_dir = lambda: Path(directory)
        app = gui.WlcRoleAclCollectorGui()
        try:
            app.maxsize(1920, 1400)
            app.geometry("1360x960+0+0")
            app.update()
            assert app.winfo_width() >= 1300 and app.winfo_height() >= 950, (
                app.geometry()
            )
            app.host_var.set("192.0.2.10")
            app.name_var.set("sample_controller")
            app.username_var.set("netops-demo")
            app.password_var.set("documentation-only")
            app.output_dir_var.set(r"C:\DocumentationDemo\WlcReports")
            app.status_var.set("문서용 합성 입력 · 실제 장비 접속 없음")
            capture_window(app, output / "01-settings.png")
            app._select_menu_tab("수집 및 분석")
            app._set_stage("reporting")
            app.status_var.set(
                "합성 raw fixture를 분석하는 단계 예시 · 실제 SSH 연결 없음"
            )
            # The stage is deliberately injected; the result below is computed from fixtures.
            app.ssh_status_var.set("오프라인 예시")
            capture_window(app, output / "02-analysis.png")
            controller = Controller(name="sample_controller", host="192.0.2.10")
            result = collect_from_offline_raw(controller, root / "tests" / "fixtures")
            parsed = build_parsed_controllers([result])
            reports = write_reports(
                parsed_controllers=parsed,
                output_dir=Path(directory),
                collection_results=[result],
            )
            summary = gui._result_report_summary_from_parsed(parsed, None, [result])
            assert summary.ssid_count > 0 and summary.role_count > 0
            assert reports["html"].is_file() and reports["xlsx"].is_file()
            app._set_result_summary(summary)
            app._set_stage("completed")
            app.status_var.set(
                "오프라인 합성 fixture 분석 완료 · 장비 운영 상태를 증명하지 않습니다."
            )
            app._select_menu_tab("보고서 관리")
            capture_window(app, output / "03-reports.png")
            app._select_menu_tab("진단 로그")
            app._log("[INFO] 문서 캡처: 네트워크 호출 차단 / 합성 fixture 전용")
            app._log(
                f"[INFO] 파서 계산 결과: SSID {summary.ssid_count}, Role {summary.role_count}"
            )
            app._log(
                f"[INFO] 수집 완전성: {summary.collection_status_label} / 실패 명령 {summary.failed_command_count}"
            )
            app._log(
                "[INFO] 생성 파일: ssid_role_acl_report.html / ssid_role_acl_report.xlsx"
            )
            app._log(
                "[WARNING] 사내 Role 대역표 미선택: 일치/불일치 0은 정책 정상 판정이 아닙니다."
            )
            capture_window(app, output / "04-log.png")
            write_manifest(
                output,
                app=gui.APP_TITLE,
                version="0.2.0",
                method="Actual CustomTkinter window / PrintWindow; synthetic stage injection; checked-in offline raw -> parser/report/summary; UI v2.0 title is distinct from package 0.2.0",
            )
        finally:
            app.destroy()


if __name__ == "__main__":
    main()

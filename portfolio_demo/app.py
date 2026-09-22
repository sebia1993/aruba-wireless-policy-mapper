from __future__ import annotations

import base64
from pathlib import Path
import sys
from datetime import datetime

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from wlc_role_acl_collector.mock_server import MockWlcServer
from wlc_role_acl_collector.web_logic import (
    WebCollectionRequest,
    WebCollectionResult,
    format_web_progress,
    run_web_collection,
)

SCENARIOS = {
    "success": {
        "label": "정상 수집",
        "file": "success_minimal.json",
        "description": "로그인부터 SSID / Role / ACL / Alias 수집과 보고서 생성까지 정상 완료합니다.",
    },
    "partial": {
        "label": "부분 수집 실패",
        "file": "partial_rights_failure.json",
        "description": "기본 설정 수집은 성공하지만 show rights 단계의 연결이 끊겨 부분 완료 상태를 확인합니다.",
    },
    "auth_failed": {
        "label": "인증 실패",
        "file": "auth_failed.json",
        "description": "Mock WLC가 인증을 거부해 실제 collector의 로그인 실패 처리 흐름을 확인합니다.",
    },
    "missing_config": {
        "label": "설정 수집 실패",
        "file": "missing_config.json",
        "description": "로그인은 성공하지만 핵심 configuration output을 받지 못한 실패 흐름을 확인합니다.",
    },
}

st.set_page_config(
    page_title="WLC Role ACL Collector · Public Demo",
    page_icon="📡",
    layout="wide",
)


def _scenario_path(key: str) -> Path:
    return REPO_ROOT / "config" / "mock_scenarios" / SCENARIOS[key]["file"]


def _render_header() -> None:
    st.title("WLC Role ACL Collector")
    st.caption("Aruba AOS8 SSID → AAA Profile → Role → ACL 분석 · 공개 Demo Mode")
    st.info(
        "실제 프로그램의 수집 → Parser → SSID/Role/ACL 분석 → 보고서 생성 흐름을 그대로 체험합니다. "
        "공개 웹에서는 운영 장비 대신 저장소의 비식별 Mock WLC를 사용하며, 실제 장비 접속과 자격 증명 입력은 비활성화합니다."
    )


def _render_sidebar() -> None:
    with st.sidebar:
        st.subheader("Demo Mode")
        st.success("실제 장비 연결: 비활성")
        st.write("분석/보고서: 원 프로젝트 코드")
        st.write("수집 대상: 로컬 Mock WLC")
        st.caption("Mock 서버는 실행 시 127.0.0.1의 임시 포트에서만 열리고 작업 종료 즉시 닫힙니다.")
        st.divider()
        st.subheader("실제 프로그램과의 차이")
        st.write("• WLC SSH/Telnet 대신 비식별 Mock 응답 사용")
        st.write("• 실제 계정/IP 입력 차단")
        st.write("• 그 이후 Parser/분석/보고서 생성은 동일 코드 사용")


def _render_input_form() -> tuple[bool, str]:
    st.subheader("수집 대상")

    scenario_key = st.selectbox(
        "체험 시나리오",
        options=list(SCENARIOS),
        format_func=lambda key: SCENARIOS[key]["label"],
        key="demo_scenario",
    )
    st.caption(SCENARIOS[scenario_key]["description"])

    protocol_col, host_col, port_col = st.columns([1.1, 1.5, 0.8])
    with protocol_col:
        st.radio(
            "접속 방식",
            ["ssh"],
            format_func=lambda _value: "SSH (실제 앱 기본)",
            horizontal=True,
            disabled=True,
            key="demo_protocol_display",
        )
    with host_col:
        st.text_input(
            "WLC IP",
            value="192.0.2.10",
            disabled=True,
            help="공개 Demo Mode의 표시용 문서 주소입니다. 실제 외부 장비에는 연결하지 않습니다.",
            key="demo_host",
        )
    with port_col:
        st.number_input(
            "접속 포트",
            min_value=1,
            max_value=65535,
            value=22,
            disabled=True,
            key="demo_port",
        )

    st.subheader("장비 계정")
    user_col, password_col, enable_col = st.columns(3)
    with user_col:
        st.text_input("장비 ID", value="demo-user", disabled=True, key="demo_username")
    with password_col:
        st.text_input(
            "장비 PW",
            value="demo-password",
            type="password",
            disabled=True,
            key="demo_password",
        )
    with enable_col:
        st.text_input(
            "Enable password (선택)",
            value="",
            type="password",
            disabled=True,
            key="demo_enable",
        )

    st.subheader("선택 입력 파일")
    st.file_uploader(
        "사내 Role 대역표 Excel",
        type=["xlsx", "xlsm"],
        disabled=True,
        help="공개 Demo Mode에서는 내부 파일 업로드를 비활성화합니다.",
        key="demo_role_networks",
    )
    st.checkbox(
        "보고서에 사내 Role 대역 비교 결과 포함",
        value=False,
        disabled=True,
        key="demo_export_local",
    )

    st.caption(
        "※ 화면 구성은 실제 Web 앱의 입력 흐름을 따르며, Demo Mode에서는 외부 접속·내부 파일 업로드만 차단합니다."
    )
    submitted = st.button(
        "수집 실행",
        type="primary",
        use_container_width=True,
        key="demo_run",
    )
    return submitted, scenario_key


def _demo_request(host: str, port: int) -> WebCollectionRequest:
    return WebCollectionRequest(
        host=host,
        controller_name="DEMO-WLC",
        protocol="telnet",
        port=port,
        username="demo-user",
        password="demo-password",
        enable_password="",
        timeout=5,
        export_local_role_networks=False,
    )


def _run_demo(scenario_key: str) -> None:
    st.session_state.pop("demo_last_result", None)
    st.session_state["demo_last_scenario"] = scenario_key
    status_box = st.empty()
    progress_bar = st.progress(0)
    log_box = st.empty()
    logs: list[str] = []

    progress_by_event = {
        "connect": 10,
        "connect_done": 20,
        "command_start": 45,
        "aliases_discovered": 60,
        "roles_discovered": 70,
        "command_done": 75,
        "complete": 90,
        "command_error": 85,
    }

    def add_log(line: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        logs.append(f"[{stamp}] {line}")
        log_box.code("\n".join(logs[-80:]), language="text")

    def on_progress(event: str, payload: dict[str, object]) -> None:
        status, line = format_web_progress(event, payload)
        if status:
            status_box.info(status)
        if line:
            add_log(line)
        progress_bar.progress(progress_by_event.get(event, 50))

    server = MockWlcServer.from_file("telnet", _scenario_path(scenario_key))
    endpoint = server.start()
    add_log(f"DEMO WLC READY scenario={scenario_key} transport=loopback:{endpoint.port}")

    try:
        with st.spinner("Mock WLC에 접속해 실제 수집·분석·보고서 파이프라인을 실행하는 중입니다."):
            result = run_web_collection(
                _demo_request(endpoint.host, endpoint.port),
                progress_callback=on_progress,
            )
    finally:
        server.stop()
        add_log("DEMO WLC CLOSED")

    progress_bar.progress(100)
    st.session_state["demo_last_result"] = result
    st.session_state["demo_last_logs"] = logs

    if result.success:
        if result.summary.get("collection_status") == "partial":
            status_box.warning("보고서는 생성되었지만 일부 수집 명령이 실패했습니다.")
        else:
            status_box.success("보고서 생성이 완료되었습니다.")
        add_log(
            "REPORT READY "
            f"status={result.summary.get('collection_status', '')} "
            f"ssid={result.summary.get('ssid_count', 0)} "
            f"role={result.summary.get('role_count', 0)}"
        )
    else:
        status_box.error("수집에 실패했습니다. 아래 오류와 진행 로그를 확인하세요.")
        add_log(
            "RUN FAILED "
            f"code={result.summary.get('error_code', 'unknown')} "
            f"stage={result.summary.get('failure_stage', 'collection')}"
        )
    st.session_state["demo_last_logs"] = logs


def _render_summary(result: WebCollectionResult) -> None:
    st.divider()
    st.subheader("결과 요약")

    summary = result.summary
    if result.success:
        if summary.get("collection_status") == "partial":
            st.warning(
                f"{summary.get('collection_status_label', '부분 완료')}: "
                f"{summary.get('recommended_action', '실패 명령을 확인하세요.')}"
            )
        else:
            st.success(str(summary.get("collection_status_label", "정상 완료")))

        metric_cols = st.columns(5)
        metric_cols[0].metric("SSID", int(summary.get("ssid_count", 0)))
        metric_cols[1].metric("Role", int(summary.get("role_count", 0)))
        metric_cols[2].metric("ACL Rule", int(summary.get("acl_rule_count", 0)))
        metric_cols[3].metric("Alias", int(summary.get("alias_count", 0)))
        metric_cols[4].metric("실패 명령", int(summary.get("failed_command_count", 0)))

        if summary.get("failed_commands"):
            st.warning(f"실패 명령: {summary['failed_commands']}")
            st.info(f"영향 영역: {summary.get('collection_impacts', '일부 수집 항목')}")
            st.info(
                "영향 범위: "
                f"Role {int(summary.get('affected_role_count', 0))}개"
                f" ({summary.get('affected_roles') or '자동 식별 없음'}), "
                f"SSID {int(summary.get('affected_ssid_count', 0))}개"
                f" ({summary.get('affected_ssids') or '자동 식별 없음'})"
            )

        st.subheader("SSID / Role 미리보기")
        if result.preview_rows:
            st.dataframe(result.preview_rows, use_container_width=True, hide_index=True)
        else:
            st.info("표시할 SSID/Role 행이 없습니다.")

        with st.expander("ACL Rule 미리보기", expanded=False):
            if result.acl_preview_rows:
                st.dataframe(result.acl_preview_rows, use_container_width=True, hide_index=True)
            else:
                st.write("표시할 ACL Rule 행이 없습니다.")

        _render_artifacts(result)
    else:
        st.error(result.error or "수집에 실패했습니다.")
        if summary:
            detail_cols = st.columns(2)
            detail_cols[0].metric("오류 코드", str(summary.get("error_code", "확인 필요")))
            detail_cols[1].metric("실패 단계", str(summary.get("failure_stage", "수집")))
            st.warning(
                str(summary.get("recommended_action", "접속 정보와 수집 로그를 확인하세요."))
            )
            with st.expander("기술 세부 정보"):
                st.json(summary)


def _render_artifacts(result: WebCollectionResult) -> None:
    st.subheader("결과 다운로드")
    st.caption("아래 파일은 Demo UI가 새로 만든 가짜 파일이 아니라 원 report.py / web_logic.py가 생성한 결과물입니다.")

    cols = st.columns(3)
    button_labels = {
        "xlsx": "Excel 보고서 다운로드",
        "csv": "CSV 매핑 다운로드",
        "html": "HTML 보고서 다운로드",
    }
    for index, key in enumerate(("xlsx", "csv", "html")):
        artifact = result.artifacts[key]
        with cols[index]:
            st.download_button(
                label=button_labels[key],
                data=artifact.data,
                file_name=artifact.filename,
                mime=artifact.media_type,
                use_container_width=True,
                key=f"demo_download_{key}",
            )

    html_artifact = result.artifacts.get("html")
    if html_artifact is None:
        return

    encoded = base64.b64encode(html_artifact.data).decode("ascii")
    st.components.v1.html(
        f"""
        <div style="font-family:Arial,sans-serif;padding:4px 0 10px">
          <a id="openReport" target="_blank"
             style="display:inline-block;background:#0f6fff;color:white;text-decoration:none;
                    padding:10px 16px;border-radius:8px;font-weight:700">
             생성된 HTML 보고서를 새 창에서 열기 ↗
          </a>
          <span style="margin-left:10px;color:#667085;font-size:13px">
             현재 실행에서 생성된 보고서
          </span>
        </div>
        <script>
          const bytes = Uint8Array.from(atob("{encoded}"), c => c.charCodeAt(0));
          const blob = new Blob([bytes], {{type: "text/html;charset=utf-8"}});
          document.getElementById("openReport").href = URL.createObjectURL(blob);
        </script>
        """,
        height=58,
    )

    with st.expander("생성된 HTML 보고서 웹 미리보기", expanded=True):
        st.components.v1.html(
            html_artifact.data.decode("utf-8", errors="replace"),
            height=760,
            scrolling=True,
        )


def _render_last_logs() -> None:
    logs = st.session_state.get("demo_last_logs")
    if not logs:
        return
    with st.expander("수집 진행 로그", expanded=True):
        st.code("\n".join(logs[-100:]), language="text")


def main() -> None:
    _render_header()
    _render_sidebar()

    submitted, scenario_key = _render_input_form()
    if submitted:
        _run_demo(scenario_key)

    result = st.session_state.get("demo_last_result")
    if isinstance(result, WebCollectionResult):
        _render_summary(result)
        _render_last_logs()


if __name__ == "__main__":
    main()

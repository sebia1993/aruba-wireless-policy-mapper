from __future__ import annotations

from pathlib import Path

import streamlit as st

from wlc_role_acl_collector.web_logic import (
    WebCollectionRequest,
    WebCollectionResult,
    format_web_progress,
    run_web_collection,
)

APP_ROOT = Path(__file__).resolve().parent
DEMO_FIXTURE = APP_ROOT / "tests" / "fixtures" / "sample_controller"

st.set_page_config(page_title="WLC Role ACL Collector · Demo Mode", layout="wide")


def _demo_request() -> WebCollectionRequest:
    return WebCollectionRequest(
        host="192.0.2.10",
        controller_name="DEMO-WLC",
        protocol="ssh",
        port=22,
        username="",
        password="",
        enable_password="",
        timeout=60,
        offline_raw_dir=DEMO_FIXTURE,
        export_local_role_networks=False,
    )


def _render_demo_settings() -> None:
    st.subheader("수집 대상")
    protocol_col, host_col, port_col = st.columns([1.0, 1.4, 0.8])
    with protocol_col:
        st.radio(
            "접속 방식",
            ["ssh"],
            index=0,
            format_func=lambda _value: "SSH · Demo Mode",
            disabled=True,
            key="demo_protocol",
        )
    with host_col:
        st.text_input("WLC IP", value="192.0.2.10", disabled=True, key="demo_host")
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
        st.text_input("장비 PW", value="demo-password", type="password", disabled=True, key="demo_password")
    with enable_col:
        st.text_input("Enable password (선택)", value="", type="password", disabled=True, key="demo_enable")

    st.caption(
        "공개 Demo Mode에서는 실제 장비 연결과 자격 증명 입력을 비활성화합니다. "
        "버튼을 누르면 저장소의 비식별 WLC fixture를 원 프로그램의 수집·파싱·보고서 파이프라인에 넣습니다."
    )


def _run_demo() -> None:
    st.session_state.pop("demo_last_result", None)
    status_box = st.empty()
    progress_bar = st.progress(0)
    log_box = st.empty()
    logs: list[str] = []

    progress_by_event = {
        "command_start": 35,
        "command_done": 70,
        "complete": 90,
    }

    def on_progress(event: str, payload: dict[str, object]) -> None:
        status, line = format_web_progress(event, payload)
        if status:
            status_box.info(status)
        if line:
            logs.append(line)
            log_box.code("\n".join(logs[-80:]), language="text")
        progress_bar.progress(progress_by_event.get(event, 50))

    with st.spinner("Demo WLC 정보를 수집하고 실제 보고서를 생성하는 중입니다."):
        result = run_web_collection(_demo_request(), progress_callback=on_progress)

    progress_bar.progress(100)
    st.session_state["demo_last_result"] = result
    if result.success:
        status_box.success("Demo 수집과 보고서 생성이 완료되었습니다.")
    else:
        status_box.error("Demo 실행에 실패했습니다.")


def _render_result(result: WebCollectionResult) -> None:
    st.divider()
    st.subheader("결과 요약")
    if not result.success:
        st.error(result.error or "실행에 실패했습니다.")
        if result.summary:
            st.json(result.summary)
        return

    summary = result.summary
    if summary.get("collection_status") == "partial":
        st.warning(str(summary.get("collection_status_label", "부분 완료")))
    else:
        st.success(str(summary.get("collection_status_label", "정상 완료")))

    metrics = st.columns(5)
    metrics[0].metric("SSID", int(summary.get("ssid_count", 0)))
    metrics[1].metric("Role", int(summary.get("role_count", 0)))
    metrics[2].metric("ACL Rule", int(summary.get("acl_rule_count", 0)))
    metrics[3].metric("Alias", int(summary.get("alias_count", 0)))
    metrics[4].metric("실패 명령", int(summary.get("failed_command_count", 0)))

    st.subheader("SSID / Role 미리보기")
    if result.preview_rows:
        st.dataframe(result.preview_rows, use_container_width=True, hide_index=True)
    else:
        st.info("표시할 SSID/Role 행이 없습니다.")

    with st.expander("ACL Rule 미리보기"):
        if result.acl_preview_rows:
            st.dataframe(result.acl_preview_rows, use_container_width=True, hide_index=True)
        else:
            st.write("표시할 ACL Rule 행이 없습니다.")

    st.subheader("결과 다운로드")
    st.caption("아래 파일도 원 프로그램의 report.py / web_logic.py가 실제로 생성한 산출물입니다.")
    cols = st.columns(3)
    for index, key in enumerate(("xlsx", "csv", "html")):
        artifact = result.artifacts[key]
        with cols[index]:
            st.download_button(
                label=artifact.filename,
                data=artifact.data,
                file_name=artifact.filename,
                mime=artifact.media_type,
                key=f"demo_download_{key}",
            )

    html_artifact = result.artifacts.get("html")
    if html_artifact is not None:
        st.subheader("생성된 HTML 보고서 미리보기")
        st.components.v1.html(
            html_artifact.data.decode("utf-8", errors="replace"),
            height=720,
            scrolling=True,
        )


def main() -> None:
    st.title("WLC Role ACL Collector")
    st.caption("실제 프로그램 흐름을 체험하는 공개 Demo Mode")

    st.info(
        "이 페이지는 별도 시뮬레이터가 아닙니다. "
        "원 프로젝트의 run_web_collection()을 Demo fixture와 함께 실행해 "
        "수집 → Parser → SSID/Role/ACL 분석 → HTML/Excel/CSV 보고서 생성을 실제로 수행합니다."
    )

    with st.sidebar:
        st.subheader("Demo Mode")
        st.success("실제 장비 연결: 비활성")
        st.write("입력 데이터: 공개 비식별 fixture")
        st.write("분석/보고서: 원 프로젝트 코드")
        st.code("tests/fixtures/sample_controller", language="text")

    _render_demo_settings()
    if st.button("수집 실행", type="primary", use_container_width=True, key="demo_run"):
        _run_demo()

    result = st.session_state.get("demo_last_result")
    if isinstance(result, WebCollectionResult):
        _render_result(result)


if __name__ == "__main__":
    main()

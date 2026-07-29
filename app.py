from __future__ import annotations

import streamlit as st

from wlc_role_acl_collector.config import default_port_for_protocol
from wlc_role_acl_collector.web_logic import (
    WebCollectionRequest,
    WebCollectionResult,
    WebCollectionBusyError,
    format_web_progress,
    run_web_collection,
)


st.set_page_config(page_title="WLC Role ACL Collector", layout="wide")


def main() -> None:
    st.title("WLC Role ACL Collector")
    st.caption("사내망 내부 공용 PC에서 실행하고, 사용자는 브라우저로 접속해 WLC Role/ACL 보고서를 생성합니다.")

    st.info(
        "인터넷 공개용 서비스가 아닙니다. 접속 주소를 아는 사내 사용자는 접근할 수 있으므로 "
        "장비 계정과 내부 대역 정보 취급에 주의하세요."
    )

    _render_sidebar_notice()
    submitted, request = _render_input_form()
    if submitted:
        _run_collection(request)

    result = st.session_state.get("last_result")
    if isinstance(result, WebCollectionResult):
        _render_result(result)


def _render_sidebar_notice() -> None:
    with st.sidebar:
        st.subheader("기본 접속 범위")
        st.code("http://127.0.0.1:8763", language="text")
        st.write("기본 설정에서는 웹앱을 실행한 PC에서만 접속할 수 있습니다.")
        st.warning(
            "다른 PC 접속을 허용하면 HTTP 구간에서 장비 계정이 보호되지 않습니다. "
            "승인된 보안 구성이 없으면 로컬 접속만 사용하세요."
        )


def _render_input_form() -> tuple[bool, WebCollectionRequest]:
    with st.form("collection_form", clear_on_submit=False):
        st.subheader("수집 대상")
        col1, col2 = st.columns(2)
        with col1:
            host = st.text_input("WLC IP 또는 Host", placeholder="192.0.2.10")
            controller_name = st.text_input("보고서 이름", placeholder="sample_controller")
            protocol = st.selectbox("Protocol", ["ssh", "telnet"], index=0)
        with col2:
            default_port = default_port_for_protocol(protocol)
            port = st.number_input("Port", min_value=1, max_value=65535, value=default_port, step=1)
            timeout = st.number_input("Timeout seconds", min_value=5, max_value=600, value=60, step=5)

        st.subheader("장비 계정")
        cred1, cred2, cred3 = st.columns(3)
        with cred1:
            username = st.text_input("Username")
        with cred2:
            password = st.text_input("Password", type="password")
        with cred3:
            enable_password = st.text_input("Enable password", type="password")

        st.subheader("선택 입력 파일")
        role_networks_file = st.file_uploader(
            "사내 Role 대역표 Excel",
            type=["xlsx", "xlsm"],
            help="Role_Networks Sheet가 있으면 우선 읽고, 없으면 첫 번째 Sheet를 읽습니다.",
        )
        export_role_networks = st.checkbox(
            "보고서에 사내 Role 대역 비교 결과 포함",
            value=role_networks_file is not None,
            help="체크하면 생성되는 HTML/Excel에 업로드한 내부 대역 정보가 포함됩니다.",
        )

        submitted = st.form_submit_button("수집 실행", type="primary")

    request = WebCollectionRequest(
        host=host,
        controller_name=controller_name,
        protocol=protocol,
        port=int(port),
        username=username,
        password=password,
        enable_password=enable_password,
        timeout=int(timeout),
        role_networks_filename=role_networks_file.name if role_networks_file else "",
        role_networks_bytes=role_networks_file.getvalue() if role_networks_file else None,
        export_local_role_networks=export_role_networks,
    )
    return submitted, request


def _run_collection(request: WebCollectionRequest) -> None:
    st.session_state.pop("last_result", None)
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
    }

    def on_progress(event: str, payload: dict[str, object]) -> None:
        status, line = format_web_progress(event, payload)
        if status:
            status_box.info(status)
        if line:
            logs.append(line)
            log_box.code("\n".join(logs[-80:]), language="text")
        progress_bar.progress(progress_by_event.get(event, 50))

    try:
        with st.spinner("WLC 정보를 수집하고 보고서를 생성하는 중입니다."):
            result = run_web_collection(request, progress_callback=on_progress)
        progress_bar.progress(100)
        st.session_state["last_result"] = result
        if result.success:
            if result.summary.get("collection_status") == "partial":
                status_box.warning("보고서는 생성되었지만 일부 수집 명령이 실패했습니다.")
            else:
                status_box.success("보고서 생성이 완료되었습니다.")
        else:
            status_box.error("수집에 실패했습니다. 오류 내용을 확인하세요.")
    except WebCollectionBusyError as exc:
        progress_bar.progress(100)
        status_box.warning(str(exc))
        logs.append(str(exc))
        log_box.code("\n".join(logs[-80:]), language="text")
    except Exception as exc:
        progress_bar.progress(100)
        status_box.error("실행 중 오류가 발생했습니다.")
        logs.append(f"{type(exc).__name__}: 실행 로그 또는 안전 진단 결과를 확인하세요.")
        log_box.code("\n".join(logs[-80:]), language="text")


def _render_result(result: WebCollectionResult) -> None:
    st.divider()
    st.subheader("결과 요약")
    if result.success:
        summary = result.summary
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
        if result.messages:
            st.write(" / ".join(result.messages))
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
            if summary.get("impact_scope_incomplete"):
                st.warning("수집 누락으로 자동 식별되지 않은 추가 영향 대상이 있을 수 있습니다.")

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
        cols = st.columns(3)
        for index, key in enumerate(("xlsx", "csv", "html")):
            artifact = result.artifacts[key]
            with cols[index]:
                st.download_button(
                    label=artifact.filename,
                    data=artifact.data,
                    file_name=artifact.filename,
                    mime=artifact.media_type,
                )
    else:
        st.error(result.error or "수집에 실패했습니다.")
        if result.summary:
            st.warning(str(result.summary.get("recommended_action", "접속 정보와 수집 로그를 확인하세요.")))
            st.json(result.summary)
        if result.messages:
            st.write(" / ".join(result.messages))


if __name__ == "__main__":
    main()

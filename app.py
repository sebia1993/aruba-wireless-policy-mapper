from __future__ import annotations

from pathlib import Path

import streamlit as st

from wlc_role_acl_collector import web_ssh_hostkey
from wlc_role_acl_collector.config import default_port_for_protocol
from wlc_role_acl_collector.diagnostics import classify_error_message
from wlc_role_acl_collector.streamlit_ui import render_role_network_sample_download
from wlc_role_acl_collector.web_logic import (
    WebCollectionRequest,
    WebCollectionResult,
    WebCollectionBusyError,
    format_web_progress,
    run_web_collection,
    validate_web_request,
)


st.set_page_config(page_title="WLC Role ACL Collector", layout="wide")


def main() -> None:
    _enforce_loopback_binding()
    st.title("WLC Role ACL Collector")
    st.caption("실행한 Windows PC에서 WLC Role/ACL 보고서를 생성하는 로컬 웹앱입니다.")

    st.info(
        "원격 공개용 서비스가 아닙니다. 앱은 loopback 주소에서만 실행되며, "
        "장비 계정과 내부 대역 정보는 현재 실행 세션에서만 입력하세요."
    )

    _render_sidebar_notice()
    submitted, request = _render_input_form()
    if submitted:
        _submit_collection(request)

    review = st.session_state.get("pending_web_ssh_host_key")
    if isinstance(review, web_ssh_hostkey.WebSSHHostKeyReview):
        _show_ssh_host_key_review(request, review)

    issue = st.session_state.get("last_collection_issue")
    if issue:
        level, message, detail = issue
        if level == "warning":
            st.warning(message)
        else:
            st.error(message)
        if detail:
            st.code(detail, language="text")

    failed_result = st.session_state.get("last_failed_result")
    if isinstance(failed_result, WebCollectionResult):
        _render_result(failed_result)
    result = st.session_state.get("last_result")
    if isinstance(result, WebCollectionResult):
        _render_result(result, previous=result.success and bool(st.session_state.get("last_attempt_failed")))


def _render_sidebar_notice() -> None:
    with st.sidebar:
        st.subheader("기본 접속 범위")
        st.code("http://127.0.0.1:8763", language="text")
        st.write("웹앱을 실행한 PC에서만 접속할 수 있습니다.")
        st.warning(
            "외부 인터페이스 바인딩은 인증·TLS가 없어 차단됩니다. "
            "여러 사용자가 접속하는 서버 형태로 배포하지 마세요."
        )


def _enforce_loopback_binding() -> None:
    address = str(st.get_option("server.address") or "localhost").strip().casefold()
    if address not in {"localhost", "127.0.0.1", "::1", "[::1]"}:
        st.error("보호되지 않은 원격 노출을 막기 위해 Streamlit은 loopback 주소에서만 실행할 수 있습니다.")
        st.stop()


def _render_input_form() -> tuple[bool, WebCollectionRequest]:
    st.subheader("수집 대상")
    protocol = st.radio(
        "접속 방식",
        ["ssh", "telnet"],
        format_func=lambda value: "SSH (기본 포트 22)" if value == "ssh" else "Telnet (기본 포트 23)",
        horizontal=True,
        key="connection_protocol",
    )
    if protocol == "telnet":
        st.warning(
            "Telnet은 계정과 장비 출력이 암호화되지 않습니다. SSH에서 Telnet으로 자동 전환하지 않으며, "
            "격리된 관리망에서 위험을 승인한 경우에만 직접 선택하세요."
        )
    st.subheader("선택 입력 파일")
    app_dir = Path(__file__).resolve().parent
    # The portable ZIP places app/app.py beside a top-level config directory.
    config_dir = app_dir / "config"
    if app_dir.name == "app" and not config_dir.is_dir():
        config_dir = app_dir.parent / "config"
    render_role_network_sample_download(config_dir)
    with st.form("collection_form", clear_on_submit=False):
        role_networks_file = st.file_uploader(
            "사내 Role 대역표 Excel",
            type=["xlsx", "xlsm"],
            help="Role_Networks 시트에 네트워크 대역과 설명을 입력하세요. IP로 대역을 찾을 때는 Role 이름을 비워도 됩니다. Role별 할당 대역을 비교할 때는 수집된 Role 이름도 입력하세요.",
        )
        export_role_networks = st.checkbox(
            "보고서에 사내 Role 대역 비교 결과 포함",
            value=False,
            key="export_local_role_networks",
            help="체크하면 보고서에 업로드한 내부 대역과 설명이 포함됩니다.",
        )

        col1, col2 = st.columns(2)
        with col1:
            host = st.text_input("WLC IP", placeholder="192.0.2.10")
            controller_name = st.text_input("보고서 표시 이름 (선택)", placeholder="sample_controller")
        with col2:
            default_port = default_port_for_protocol(protocol)
            port = st.number_input(
                "접속 포트",
                min_value=1,
                max_value=65535,
                value=default_port,
                step=1,
                key=f"connection_port_{protocol}",
            )
            timeout = st.number_input("명령 Timeout (초)", min_value=5, max_value=600, value=60, step=5)

        st.subheader("장비 계정")
        cred1, cred2, cred3 = st.columns(3)
        with cred1:
            username = st.text_input("장비 ID")
        with cred2:
            password = st.text_input("장비 PW", type="password")
        with cred3:
            enable_password = st.text_input("Enable password (선택)", type="password")

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


def _submit_collection(request: WebCollectionRequest) -> None:
    """SSH must pass a credential-free server-key review before collection."""
    st.session_state.pop("last_collection_issue", None)
    st.session_state.pop("pending_web_ssh_host_key", None)
    st.session_state.pop("web_ssh_verified", None)
    if request.protocol.strip().lower() != "ssh":
        _run_collection(request)
        return
    try:
        validate_web_request(request)
    except ValueError as exc:
        st.session_state["last_attempt_failed"] = True
        st.error(f"입력값을 확인하세요: {exc}")
        return

    try:
        review = web_ssh_hostkey.inspect_ssh_host_key(
            request.host, request.port, timeout=request.timeout
        )
    except Exception:
        st.session_state["last_attempt_failed"] = True
        st.error("SSH 서버 키 사전 확인에 실패했습니다.")
        st.info("WLC의 SSH 서비스 및 관리망 연결을 확인하세요. 로그인 정보는 전송하지 않았습니다.")
        return

    if review.state == "trusted":
        _run_collection(request)
    elif review.state == "unknown":
        st.session_state["pending_web_ssh_host_key"] = review
        st.session_state["last_attempt_failed"] = True
    else:
        st.session_state["last_attempt_failed"] = True
        st.error("WLC-SEC-003: 이전에 승인된 SSH 서버 키와 현재 키가 다릅니다. 연결을 차단했습니다.")
        st.warning("장비 교체·초기화 여부와 지문을 관리자에게 확인하세요. 자동 재승인은 지원하지 않습니다.")


def _show_ssh_host_key_review(
    request: WebCollectionRequest, review: web_ssh_hostkey.WebSSHHostKeyReview
) -> None:
    observation = review.observation
    if (
        request.protocol.strip().lower() != "ssh"
        or request.host.strip() != observation.host
        or request.port != observation.port
    ):
        st.session_state.pop("pending_web_ssh_host_key", None)
        st.warning("접속 대상 또는 방식이 바뀌어 이전 지문 승인을 취소했습니다.")
        return

    # Streamlit >=1.37 provides a browser modal. Older supported versions
    # receive exactly the same explicit approval controls in an inline panel.
    dialog = getattr(st, "dialog", None)
    if callable(dialog):
        dialog("SSH 서버 키 최초 승인")(_render_ssh_host_key_review_body)(request, review)
    else:
        with st.container(border=True):
            st.subheader("SSH 서버 키 최초 승인")
            _render_ssh_host_key_review_body(request, review)


def _render_ssh_host_key_review_body(
    request: WebCollectionRequest, review: web_ssh_hostkey.WebSSHHostKeyReview
) -> None:
    observation = review.observation
    st.warning("처음 접속하는 SSH 장비입니다. 로그인 정보를 전송하기 전에 서버 키를 확인해야 합니다.")
    st.write(f"대상: `{observation.lookup_name}`")
    st.write(f"키 종류: `{observation.key_type}`")
    st.write("SHA-256 서버 키 지문:")
    st.code(observation.fingerprint, language="text")
    st.info("WLC 관리 화면이나 담당자를 통해 지문을 별도로 확인하고, 완전히 일치하는 경우에만 승인하세요.")
    verified = st.checkbox(
        "별도 관리 경로로 확인한 지문과 완전히 일치합니다.",
        value=False,
        key="web_ssh_verified",
    )
    approve, reject = st.columns(2)
    with approve:
        if st.button(
            "지문 승인 후 수집 실행",
            key="web_ssh_approve",
            disabled=not verified,
            type="primary",
            use_container_width=True,
        ):
            try:
                validate_web_request(request)
                web_ssh_hostkey.approve_reviewed_ssh_host_key(
                    review,
                    host=request.host,
                    port=request.port,
                    timeout=request.timeout,
                )
            except Exception:
                st.session_state.pop("pending_web_ssh_host_key", None)
                st.session_state["last_attempt_failed"] = True
                st.error(
                    "SSH 서버 키 승인에 실패했습니다. 지문·대상·포트 또는 키 저장 상태가 "
                    "변경되었을 수 있습니다. 로그인을 시도하지 않았으므로 다시 확인해 주세요."
                )
            else:
                st.session_state.pop("pending_web_ssh_host_key", None)
                _run_collection(request)
                st.rerun()
    with reject:
        if st.button(
            "승인 거부 / 접속 취소",
            key="web_ssh_reject",
            use_container_width=True,
        ):
            st.session_state.pop("pending_web_ssh_host_key", None)
            st.session_state["last_attempt_failed"] = True
            st.rerun()


def _run_collection(request: WebCollectionRequest) -> None:
    previous = st.session_state.get("last_result")
    preserve_previous = isinstance(previous, WebCollectionResult) and previous.success
    if not preserve_previous:
        st.session_state.pop("last_result", None)
    st.session_state.pop("last_failed_result", None)
    st.session_state["last_attempt_failed"] = True
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
        if result.success or not preserve_previous:
            st.session_state["last_result"] = result
        else:
            st.session_state["last_failed_result"] = result
        st.session_state["last_attempt_failed"] = not result.success
        if result.success:
            if result.summary.get("collection_status") == "partial":
                status_box.warning("보고서는 생성되었지만 일부 수집 명령이 실패했습니다.")
            else:
                status_box.success("보고서 생성이 완료되었습니다.")
        else:
            status_box.error("수집에 실패했습니다. 오류 내용을 확인하세요.")
    except WebCollectionBusyError as exc:
        st.session_state["last_collection_issue"] = ("warning", str(exc), "")
    except ValueError as exc:
        st.session_state["last_collection_issue"] = ("error", "입력값을 확인하세요.", str(exc))
    except Exception as exc:
        failure = classify_error_message(str(exc))
        st.session_state["last_collection_issue"] = (
            "error", failure.title, f"오류 코드: {failure.code}\n{failure.suggestion}"
        )
    progress_bar.progress(100)


def _render_result(result: WebCollectionResult, *, previous: bool = False) -> None:
    st.divider()
    st.subheader("이전 성공 결과" if previous else "결과 요약")
    if previous:
        st.warning("이번 수집은 완료되지 않았습니다. 아래는 이전에 생성한 결과이며 계속 내려받을 수 있습니다.")
        st.caption(f"이전 결과 실행 ID: {result.run_id}")
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
        comparison = summary.get("role_name_comparison")
        if comparison:
            st.markdown("**사내 대역표 Role 이름 비교**")
            st.text(
                f"시트 {comparison['sheet']} · Excel Role {comparison['excel_count']}개 · "
                f"수집 Role {comparison['collected_count']}개 · 이름 일치 {comparison['matched_count']}개"
            )
            if comparison["wlc_only_count"]:
                st.text(
                    f"대역표에 없는 수집 Role {comparison['wlc_only_count']}개 (최대 5개 표시) · "
                    + ", ".join(comparison["wlc_only_examples"])
                )
            if comparison["excel_only_count"]:
                st.text(
                    f"이번 수집에서 찾지 못한 Excel Role {comparison['excel_only_count']}개 (최대 5개 표시) · "
                    + ", ".join(comparison["excel_only_examples"])
                )
            if comparison["wlc_only_count"] or comparison["excel_only_count"]:
                st.caption("Role 이름은 할당 대역을 비교할 때 사용합니다. IP 대역 설명은 Role 이름이 달라도 주소로 찾습니다.")
        elif summary.get("role_network_rows"):
            st.caption("Role 이름이 없는 대역표입니다. 보고서에 포함하면 주소를 기준으로 대역 설명을 찾습니다.")
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
            summary = result.summary
            detail_cols = st.columns(2)
            detail_cols[0].metric("오류 코드", str(summary.get("error_code", "확인 필요")))
            detail_cols[1].metric("실패 단계", str(summary.get("failure_stage", "수집")))
            st.warning(str(summary.get("recommended_action", "접속 정보와 수집 로그를 확인하세요.")))
            with st.expander("기술 세부 정보"):
                st.json(summary)
        if result.messages:
            st.write(" / ".join(result.messages))


if __name__ == "__main__":
    main()

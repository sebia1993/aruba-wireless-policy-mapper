from wlc_role_acl_collector.diagnostic_codes import classify_message_to_code, get_diagnostic_code
from wlc_role_acl_collector.diagnostics import classify_error_message


def test_known_diagnostic_code_contains_safe_operator_guidance():
    code = get_diagnostic_code("WLC-CMD-001")

    assert code.stage == "DGN-CMD"
    assert "show configuration effective" in code.operator_action


def test_message_classification_returns_stable_code():
    code = classify_message_to_code("TCP connection to device failed with timeout", command_id="connect")

    assert code.code == "WLC-NET-001"


def test_enable_failure_is_classified_before_generic_password_failure():
    code = classify_message_to_code("enable password failed", command_id="enable")

    assert code.code == "WLC-AUTH-002"


def test_legacy_failure_info_exposes_new_code():
    info = classify_error_message("Authentication failed: bad password")

    assert info.category == "authentication"
    assert info.code == "WLC-AUTH-001"


def test_ssh_host_key_errors_have_specific_security_codes():
    from wlc_role_acl_collector.diagnostic_codes import classify_message_to_code
    assert classify_message_to_code("미승인 SSH 서버 키입니다. GUI 또는 Web에서 승인하세요.").code == "WLC-SEC-002"
    assert classify_message_to_code("승인된 SSH 서버 키와 현재 키가 달라 연결을 차단했습니다.").code == "WLC-SEC-003"
    assert classify_message_to_code("SSH 서버 키를 안전하게 확인하지 못했습니다.").code == "WLC-SEC-004"


def test_gui_ssh_key_errors_get_security_guidance_instead_of_unknown():
    from wlc_role_acl_collector.diagnostics import classify_error_message
    mismatch = classify_error_message("승인된 SSH 서버 키와 현재 키가 달라 연결을 차단했습니다.")
    assert mismatch.code == "WLC-SEC-003"
    assert mismatch.category == "security"
    assert "지문" in mismatch.suggestion
    timeout = classify_error_message("SSH 서버 키를 안전하게 확인하지 못했습니다.")
    assert timeout.code == "WLC-SEC-004"

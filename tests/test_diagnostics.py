from wlc_role_acl_collector.diagnostics import classify_error_message, summarize_collection_failure
from wlc_role_acl_collector.models import CollectionResult, CommandOutput, Controller


def test_classifies_authentication_failure():
    info = classify_error_message("Authentication failed: bad password")

    assert info.category == "authentication"
    assert info.code == "WLC-AUTH-001"
    assert "오류 코드: WLC-AUTH-001" in info.as_text()
    assert "ID/PW" in info.suggestion


def test_classifies_timeout_failure():
    info = classify_error_message("TCP connection to device failed. Intermediate firewall blocking access.")

    assert info.category == "timeout"
    assert "WLC IP" in info.suggestion


def test_classifies_enable_failure_separately_from_login_failure():
    info = classify_error_message("enable password failed")

    assert info.category == "enable_authentication"
    assert info.code == "WLC-AUTH-002"
    assert "enable password" in info.suggestion


def test_summarizes_missing_config_as_command_failure():
    result = CollectionResult(controller=Controller(name="wlc", host="192.0.2.10"))
    result.commands.append(
        CommandOutput(
            command_id="configuration_effective",
            command="show configuration effective",
            success=False,
            error="Invalid input: show configuration effective",
        )
    )

    info = summarize_collection_failure(result)

    assert info.category == "command"

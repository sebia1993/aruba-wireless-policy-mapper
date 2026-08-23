import pytest

from wlc_role_acl_collector.validation import (
    MAX_COLLECTION_DURATION_SECONDS,
    build_show_netdestination_command,
    build_show_rights_command,
    validate_port,
    validate_timeout_seconds,
    validate_wlc_address,
)


@pytest.mark.parametrize(
    "value",
    ["10.10.10.10", "2001:db8::10", "wlc01.example.internal"],
)
def test_validate_wlc_address_accepts_ip_and_compatible_hostname(value):
    assert validate_wlc_address(value) == value


@pytest.mark.parametrize(
    "value",
    ["", "10.10.10.10/path", "https://10.10.10.10", "bad host", "-wlc.example"],
)
def test_validate_wlc_address_rejects_blank_url_path_and_malformed_host(value):
    with pytest.raises(ValueError):
        validate_wlc_address(value)


def test_validate_timeout_uses_explicit_supported_range():
    assert validate_timeout_seconds(5) == 5
    assert validate_timeout_seconds("600") == 600
    with pytest.raises(ValueError, match="5에서 600"):
        validate_timeout_seconds(4)
    with pytest.raises(ValueError, match="5에서 600"):
        validate_timeout_seconds(601)
    assert MAX_COLLECTION_DURATION_SECONDS == 3600


def test_validate_port_rejects_out_of_range_and_non_numeric_values():
    assert validate_port("22") == 22
    with pytest.raises(ValueError, match="1에서 65535"):
        validate_port(0)
    with pytest.raises(ValueError, match="숫자"):
        validate_port("ssh")


def test_dynamic_show_commands_quote_spaces_without_changing_safe_identifiers():
    assert build_show_rights_command("corp-employee") == "show rights corp-employee"
    assert build_show_rights_command("corp employee") == 'show rights "corp employee"'
    assert build_show_netdestination_command("dns_alias") == "show netdestination dns_alias"


@pytest.mark.parametrize(
    "value",
    [
        'corp"; reload',
        "corp; reload",
        "corp && reload",
        "corp || reload",
        "corp\nshow running-config",
        "corp\r\nreload",
        " corp",
        "corp ",
        "corp\\reload",
    ],
)
def test_dynamic_show_commands_reject_cli_injection_boundaries(value):
    with pytest.raises(ValueError, match="차단"):
        build_show_rights_command(value)
    with pytest.raises(ValueError, match="차단"):
        build_show_netdestination_command(value)

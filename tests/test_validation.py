import pytest

from wlc_role_acl_collector.validation import (
    MAX_COLLECTION_DURATION_SECONDS,
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

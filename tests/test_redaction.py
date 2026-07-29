from wlc_role_acl_collector.redaction import Redactor, redaction_self_test


def test_redaction_masks_sensitive_values_with_stable_labels():
    redacted = Redactor().redact(
        "controller wlc-prod-01 host 10.10.10.10 password Secret123 "
        "snmp-server community public aa:bb:cc:dd:ee:ff"
    )

    assert "10.10.10.10" not in redacted
    assert "Secret123" not in redacted
    assert "public" not in redacted
    assert "aa:bb:cc:dd:ee:ff" not in redacted.casefold()
    assert "wlc-prod-01" not in redacted
    assert "<IP:1>" in redacted
    assert "<MAC:1>" in redacted
    assert "<HOST:1>" in redacted


def test_redaction_self_test_passes():
    assert redaction_self_test()


def test_redaction_masks_dynamic_role_and_alias_command_identifiers():
    redactor = Redactor()

    redacted = redactor.redact(
        "rights::finance-employee | show rights finance-employee | "
        "netdestination::payroll-servers | show netdestination payroll-servers"
    )

    assert "finance-employee" not in redacted
    assert "payroll-servers" not in redacted
    assert "rights::<ROLE:1>" in redacted
    assert "show rights <ROLE:1>" in redacted
    assert "netdestination::<ALIAS:1>" in redacted
    assert "show netdestination <ALIAS:1>" in redacted

from wlc_role_acl_collector.collection_health import (
    COLLECTION_COMPLETED,
    COLLECTION_FAILED,
    COLLECTION_PARTIAL,
    assess_collection_results,
    assess_command_status_rows,
    infer_collection_impact_scope,
)
from wlc_role_acl_collector.models import CollectionResult, CommandOutput, Controller


def _result(*commands: CommandOutput) -> CollectionResult:
    return CollectionResult(
        controller=Controller(name="wlc-a", host="192.0.2.10"),
        commands=list(commands),
    )


def test_collection_health_is_completed_when_all_commands_succeed():
    health = assess_collection_results(
        [
            _result(
                CommandOutput(
                    command_id="configuration_effective",
                    command="show configuration effective",
                    output="configuration data",
                ),
                CommandOutput(command_id="user_table", command="show user-table", output="users"),
            )
        ]
    )

    assert health.status == COLLECTION_COMPLETED
    assert health.label_ko == "정상 완료"
    assert health.failed_command_count == 0
    assert health.impact_areas == ()


def test_collection_health_is_partial_and_explains_optional_command_impact():
    health = assess_collection_results(
        [
            _result(
                CommandOutput(
                    command_id="configuration_effective",
                    command="show configuration effective",
                    output="configuration data",
                ),
                CommandOutput(
                    command_id="user_table",
                    command="show user-table",
                    success=False,
                    error="timeout",
                ),
                CommandOutput(
                    command_id="rights::employee",
                    command="show rights employee",
                    success=False,
                    error="timeout",
                ),
            )
        ]
    )

    assert health.status == COLLECTION_PARTIAL
    assert health.failed_command_count == 2
    assert health.impact_areas == ("Role별 관측 사용자 수", "Role 적용 ACL")
    assert "확정된 값" in health.recommended_action_ko


def test_collection_health_is_failed_when_required_output_is_empty():
    health = assess_collection_results(
        [
            _result(
                CommandOutput(
                    command_id="configuration_effective",
                    command="show configuration effective",
                    output="",
                )
            )
        ]
    )

    assert health.status == COLLECTION_FAILED
    assert health.required_missing_controllers == ("wlc-a",)
    assert "SSID·Role·ACL 기준 설정" in health.impact_areas


def test_disconnect_failure_is_visible_without_claiming_role_or_ssid_impact():
    health = assess_collection_results(
        [
            _result(
                CommandOutput(
                    command_id="configuration_effective",
                    command="show configuration effective",
                    output="configuration data",
                ),
                CommandOutput(
                    command_id="disconnect",
                    command="disconnect",
                    success=False,
                    error="socket cleanup failed",
                ),
            )
        ]
    )
    scope = infer_collection_impact_scope(
        [{"controller": "wlc-a", "command_id": "disconnect", "success": False}],
        [{"controller": "wlc-a", "role": "employee"}],
        [{"controller": "wlc-a", "role": "employee", "ssid": "CORP"}],
    )

    assert health.status == COLLECTION_PARTIAL
    assert health.impact_areas == ("장비 세션 정리",)
    assert "세션 종료" in health.recommended_action_ko
    assert scope.affected_roles == ()
    assert scope.affected_ssids == ()
    assert scope.identification_incomplete is False


def test_report_rows_accept_string_boolean_and_detect_partial_collection():
    health = assess_command_status_rows(
        [
            {
                "controller": "wlc-a",
                "command_id": "configuration_effective",
                "success": "True",
            },
            {
                "controller": "wlc-a",
                "command_id": "netdestination::servers",
                "success": "False",
            },
        ]
    )

    assert health.status == COLLECTION_PARTIAL
    assert health.failed_command_ids == ("netdestination::servers",)
    assert health.impact_areas == ("Alias 상세 주소",)


def test_report_rows_detect_explicit_required_command_failure():
    health = assess_command_status_rows(
        [
            {
                "controller": "wlc-a",
                "command_id": "configuration_effective",
                "success": False,
            }
        ]
    )

    assert health.status == COLLECTION_FAILED
    assert health.required_missing_controllers == ("wlc-a",)


def test_impact_scope_maps_failed_role_command_to_role_and_ssid():
    scope = infer_collection_impact_scope(
        [
            {
                "controller": "wlc-a",
                "command_id": "rights::employee",
                "success": False,
            }
        ],
        [{"controller": "wlc-a", "role": "employee", "source": "any", "destination": "any"}],
        [{"controller": "wlc-a", "role": "employee", "ssid": "CORP"}],
    )

    assert scope.affected_roles == ("employee",)
    assert scope.affected_ssids == ("CORP",)
    assert scope.identification_incomplete is False


def test_impact_scope_maps_failed_alias_to_referencing_acl_roles():
    scope = infer_collection_impact_scope(
        [
            {
                "controller": "wlc-a",
                "command_id": "netdestination::internal-servers",
                "success": "False",
            }
        ],
        [
            {
                "controller": "wlc-a",
                "role": "employee",
                "source": "user",
                "destination": "alias internal-servers",
            },
            {
                "controller": "wlc-a",
                "role": "guest",
                "source": "user",
                "destination": "any",
            },
        ],
        [
            {"controller": "wlc-a", "role": "employee", "ssid": "CORP"},
            {"controller": "wlc-a", "role": "guest", "ssid": "GUEST"},
        ],
    )

    assert scope.affected_roles == ("employee",)
    assert scope.affected_ssids == ("CORP",)
    assert scope.identification_incomplete is False


def test_impact_scope_marks_unknown_alias_and_duration_scope_conservatively():
    unknown_alias_scope = infer_collection_impact_scope(
        [{"controller": "wlc-a", "command_id": "netdestination::missing", "success": False}],
        [],
        [],
    )
    duration_scope = infer_collection_impact_scope(
        [{"controller": "wlc-a", "command_id": "duration_limit", "success": False}],
        [{"controller": "wlc-a", "role": "employee"}],
        [{"controller": "wlc-a", "role": "employee", "ssid": "CORP"}],
    )

    assert unknown_alias_scope.identification_incomplete is True
    assert duration_scope.affected_roles == ("employee",)
    assert duration_scope.affected_ssids == ("CORP",)
    assert duration_scope.identification_incomplete is True


def test_unknown_failure_scope_does_not_mark_other_controllers_as_affected():
    scope = infer_collection_impact_scope(
        [{"controller": "wlc-a", "command_id": "parse_runtime", "success": False}],
        [
            {"controller": "wlc-a", "role": "employee"},
            {"controller": "wlc-b", "role": "guest"},
        ],
        [
            {"controller": "wlc-a", "role": "employee", "ssid": "CORP"},
            {"controller": "wlc-b", "role": "guest", "ssid": "GUEST"},
        ],
    )

    assert scope.affected_roles == ("employee",)
    assert scope.affected_ssids == ("CORP",)
    assert scope.identification_incomplete is True

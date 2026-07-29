"""Classify collection completeness for every user interface.

The collector can still create a useful report when an optional command fails.
Keeping this decision here prevents the GUI, CLI, web UI, and HTML report from
describing the same run differently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .models import CollectionResult, ParsedController


COLLECTION_COMPLETED = "completed"
COLLECTION_PARTIAL = "partial"
COLLECTION_FAILED = "failed"
REQUIRED_COMMAND_ID = "configuration_effective"


@dataclass(frozen=True)
class CollectionHealth:
    """A user-facing summary of whether collected evidence is complete."""

    status: str
    failed_command_ids: tuple[str, ...] = ()
    required_missing_controllers: tuple[str, ...] = ()
    impact_areas: tuple[str, ...] = ()

    @property
    def failed_command_count(self) -> int:
        return len(self.failed_command_ids)

    @property
    def label_ko(self) -> str:
        return {
            COLLECTION_COMPLETED: "정상 완료",
            COLLECTION_PARTIAL: "부분 완료",
            COLLECTION_FAILED: "수집 실패",
        }[self.status]

    @property
    def recommended_action_ko(self) -> str:
        if self.status == COLLECTION_FAILED:
            return "보고서를 정책 판단에 사용하지 말고 접속·인증·필수 명령 문제를 해결한 뒤 다시 수집하세요."
        if self.status == COLLECTION_PARTIAL:
            if set(self.failed_command_ids) == {"disconnect"}:
                return "보고서 데이터는 생성됐지만 장비 세션 종료를 확인하지 못했습니다. 프로그램을 종료하고 WLC 관리 세션 상태를 확인하세요."
            return "실패 명령과 영향 영역을 확인하고, 해당 정보는 재수집 전까지 확정된 값으로 판단하지 마세요."
        return "필수 및 선택 수집 명령이 모두 완료되었습니다. Unresolved 항목은 별도로 확인하세요."

    @property
    def impact_text_ko(self) -> str:
        if not self.impact_areas:
            return "수집 누락 영향 없음"
        return ", ".join(self.impact_areas)


@dataclass(frozen=True)
class CollectionImpactScope:
    """Known Role/SSID rows whose report data depends on failed commands."""

    affected_roles: tuple[str, ...] = ()
    affected_ssids: tuple[str, ...] = ()
    identification_incomplete: bool = False

    @property
    def role_count(self) -> int:
        return len(self.affected_roles)

    @property
    def ssid_count(self) -> int:
        return len(self.affected_ssids)


def assess_collection_results(results: Iterable[CollectionResult]) -> CollectionHealth:
    """Assess one or more live/offline collection results."""

    result_list = list(results)
    if not result_list:
        return CollectionHealth(
            status=COLLECTION_FAILED,
            required_missing_controllers=("수집 대상 없음",),
            impact_areas=(_impact_area(REQUIRED_COMMAND_ID),),
        )

    failed_command_ids: list[str] = []
    required_missing_controllers: list[str] = []
    impact_areas: list[str] = []

    for result in result_list:
        for command in result.commands:
            if not command.success:
                failed_command_ids.append(command.command_id)
                _append_unique(impact_areas, _impact_area(command.command_id))
        if not result.command_output(REQUIRED_COMMAND_ID).strip():
            required_missing_controllers.append(result.controller.name)
            _append_unique(impact_areas, _impact_area(REQUIRED_COMMAND_ID))

    if required_missing_controllers:
        status = COLLECTION_FAILED
    elif failed_command_ids:
        status = COLLECTION_PARTIAL
    else:
        status = COLLECTION_COMPLETED

    return CollectionHealth(
        status=status,
        failed_command_ids=tuple(failed_command_ids),
        required_missing_controllers=tuple(required_missing_controllers),
        impact_areas=tuple(impact_areas),
    )


def infer_collection_impact_scope(
    command_rows: Iterable[Mapping[str, object]],
    acl_rows: Iterable[Mapping[str, object]],
    ssid_rows: Iterable[Mapping[str, object]],
) -> CollectionImpactScope:
    """Map failed command IDs to known Role and SSID rows.

    The result is intentionally conservative. ``identification_incomplete`` is
    set when a failed dynamic command cannot be tied to an ACL row, or when a
    broad failure may have prevented undiscovered objects from being collected.
    """

    command_row_list = list(command_rows)
    acl_row_list = list(acl_rows)
    ssid_row_list = list(ssid_rows)
    affected_roles: set[str] = set()
    affected_ssids: set[str] = set()
    identification_incomplete = False
    for command_row in command_row_list:
        if _bool_value(command_row.get("success"), default=True):
            continue
        command_id = str(command_row.get("command_id") or "").strip()
        controller = str(command_row.get("controller") or "").strip().casefold()
        controller_acl_rows = _rows_for_controller(acl_row_list, controller)
        controller_ssid_rows = _rows_for_controller(ssid_row_list, controller)

        if command_id.startswith("rights::"):
            role = command_id.split("::", 1)[1].strip()
            if role:
                affected_roles.add(role)
                affected_ssids.update(_ssids_for_roles(controller_ssid_rows, {role}))
            else:
                identification_incomplete = True
            continue

        if command_id.startswith("netdestination::"):
            alias = command_id.split("::", 1)[1].strip()
            alias_roles = {
                str(row.get("role") or "").strip()
                for row in controller_acl_rows
                if str(row.get("role") or "").strip()
                and (
                    _acl_field_references_alias(row.get("source"), alias)
                    or _acl_field_references_alias(row.get("destination"), alias)
                )
            }
            if alias_roles:
                affected_roles.update(alias_roles)
                affected_ssids.update(_ssids_for_roles(controller_ssid_rows, alias_roles))
            else:
                identification_incomplete = True
            continue

        if command_id in {
            "connect",
            "enable",
            "disable_paging",
            REQUIRED_COMMAND_ID,
            "ip_interface_brief",
            "user_table",
            "duration_limit",
            "cancelled",
        }:
            affected_roles.update(
                str(row.get("role") or "").strip()
                for row in (*controller_acl_rows, *controller_ssid_rows)
                if str(row.get("role") or "").strip()
            )
            affected_ssids.update(
                str(row.get("ssid") or "").strip()
                for row in controller_ssid_rows
                if str(row.get("ssid") or "").strip()
            )
            if command_id in {"connect", REQUIRED_COMMAND_ID, "duration_limit", "cancelled"}:
                identification_incomplete = True
            continue

        if command_id not in {"clock", "version", "disconnect"}:
            affected_roles.update(
                str(row.get("role") or "").strip()
                for row in (*controller_acl_rows, *controller_ssid_rows)
                if str(row.get("role") or "").strip()
            )
            affected_ssids.update(
                str(row.get("ssid") or "").strip()
                for row in controller_ssid_rows
                if str(row.get("ssid") or "").strip()
            )
            identification_incomplete = True

    return CollectionImpactScope(
        affected_roles=tuple(sorted(affected_roles, key=str.casefold)),
        affected_ssids=tuple(sorted(affected_ssids, key=str.casefold)),
        identification_incomplete=identification_incomplete,
    )


def infer_collection_impact_scope_for_parsed(
    results: Iterable[CollectionResult],
    parsed_controllers: Iterable[ParsedController],
) -> CollectionImpactScope:
    command_rows: list[dict[str, object]] = []
    acl_rows: list[dict[str, object]] = []
    ssid_rows: list[dict[str, object]] = []
    for result in results:
        command_rows.extend(result.command_status_rows())
    for parsed in parsed_controllers:
        for policy in parsed.role_policies.values():
            for rule in policy.rules:
                acl_rows.append(
                    {
                        "controller": policy.controller,
                        "role": policy.role,
                        "source": rule.source,
                        "destination": rule.destination,
                    }
                )
        for mapping in parsed.ssid_role_mappings:
            ssid_rows.append(
                {
                    "controller": mapping.controller,
                    "role": mapping.role,
                    "ssid": mapping.ssid,
                }
            )
    return infer_collection_impact_scope(command_rows, acl_rows, ssid_rows)


def assess_command_status_rows(rows: Iterable[Mapping[str, object]]) -> CollectionHealth:
    """Assess command rows already embedded in an Excel/HTML report.

    A generated report normally contains a successful required command. For
    hand-built or older report data, absence alone is not treated as failure;
    only an explicit failed required row changes the status to ``failed``.
    """

    failed_command_ids: list[str] = []
    required_missing_controllers: list[str] = []
    impact_areas: list[str] = []

    for row in rows:
        if _bool_value(row.get("success"), default=True):
            continue
        command_id = str(row.get("command_id") or "").strip() or "unknown"
        failed_command_ids.append(command_id)
        _append_unique(impact_areas, _impact_area(command_id))
        if command_id == REQUIRED_COMMAND_ID:
            controller = str(row.get("controller") or "unknown").strip() or "unknown"
            _append_unique(required_missing_controllers, controller)

    if required_missing_controllers:
        status = COLLECTION_FAILED
    elif failed_command_ids:
        status = COLLECTION_PARTIAL
    else:
        status = COLLECTION_COMPLETED

    return CollectionHealth(
        status=status,
        failed_command_ids=tuple(failed_command_ids),
        required_missing_controllers=tuple(required_missing_controllers),
        impact_areas=tuple(impact_areas),
    )


def _impact_area(command_id: str) -> str:
    if command_id == REQUIRED_COMMAND_ID:
        return "SSID·Role·ACL 기준 설정"
    if command_id.startswith("rights::"):
        return "Role 적용 ACL"
    if command_id.startswith("netdestination::"):
        return "Alias 상세 주소"
    return {
        "connect": "장비 접속",
        "cancelled": "사용자 취소",
        "duration_limit": "전체 수집 완전성",
        "enable": "권한 상승",
        "disable_paging": "긴 출력의 완전성",
        "clock": "장비 시간",
        "version": "장비 버전",
        "ip_interface_brief": "VLAN·인터페이스 대역",
        "user_table": "Role별 관측 사용자 수",
        "disconnect": "장비 세션 정리",
        "collection_runtime": "대상 WLC 전체 수집",
        "parse_runtime": "수집 결과 해석",
    }.get(command_id, "일부 수집 항목")


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _rows_for_controller(
    rows: list[Mapping[str, object]],
    controller: str,
) -> list[Mapping[str, object]]:
    if not controller:
        return rows
    return [
        row
        for row in rows
        if str(row.get("controller") or "").strip().casefold() == controller
    ]


def _ssids_for_roles(
    ssid_rows: list[Mapping[str, object]],
    roles: set[str],
) -> set[str]:
    role_keys = {role.casefold() for role in roles}
    return {
        str(row.get("ssid") or "").strip()
        for row in ssid_rows
        if str(row.get("role") or "").strip().casefold() in role_keys
        and str(row.get("ssid") or "").strip()
    }


def _acl_field_references_alias(value: object, alias: str) -> bool:
    if not alias:
        return False
    normalized = " ".join(str(value or "").strip().split())
    if normalized.casefold().startswith("alias "):
        normalized = normalized[6:].strip()
    return normalized.casefold() == alias.casefold()


def _bool_value(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().casefold()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return default

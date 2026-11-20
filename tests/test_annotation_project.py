import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from wlc_role_acl_collector.models import (
    AclRule, CollectionResult, CommandOutput, Controller, NetDestinationEntry,
    ParsedController, RolePolicy, SsidRoleMapping, UserRoleObservation,
)


def build(*args, **kwargs):
    from wlc_role_acl_collector.annotation_project import build_annotation_project

    return build_annotation_project(*args, **kwargs)


def parsed(host="192.0.2.1", *, name="same", port=22, service="any"):
    controller = Controller(name, host, port=port, password_env="SECRET_ENV")
    item = ParsedController(controller)
    item.role_policies["staff"] = RolePolicy(
        name, "staff", ["first", "staff"],
        [AclRule(name, "staff", 10, f"user alias servers {service} permit log", "permit", "user", "alias servers", service)],
        raw_lines=["session-acl first", "access-list session staff position 20", "password MUST_NOT_EXPORT"],
    )
    item.role_policies["empty"] = RolePolicy(name, "empty")
    item.netdestination_aliases["servers"] = [NetDestinationEntry(name, "servers", 1, "host", host, f"host {host}")]
    item.user_role_observations["staff"] = UserRoleObservation(name, "staff", 3)
    item.ssid_role_mappings = [SsidRoleMapping(name, "ap", "vap", "profile", f"wifi-{host}", "aaa", "default", "staff", "", "", "")]
    return item


def successful(item, *extra):
    return CollectionResult(item.controller, [CommandOutput("configuration_effective", "show configuration effective", output="policy"), *extra])


def test_parsed_controllers_with_duplicate_names_never_mix_policies_or_aliases():
    first, second = parsed(), parsed("192.0.2.2")
    second.role_policies["staff"].rules[0].raw = "second rule permit log"
    misleading_frames = {"Role_ACL_Detail": pd.DataFrame([{"controller": "same", "role": "staff", "raw_rule": "MIXED"}])}
    project = build(misleading_frames, parsed_controllers=[first, second], collection_results=[successful(second), successful(first)])
    snapshot = project["snapshot"]
    controllers = {row["id"]: row for row in snapshot["controllers"]}
    assert len(controllers) == 2
    for rule in snapshot["rules"]:
        host = controllers[rule["controllerId"]]["host"]
        assert rule["raw"] == ("user alias servers any permit log" if host == "192.0.2.1" else "second rule permit log")
        alias = next(a for a in snapshot["aliases"] if a["controllerId"] == rule["controllerId"])
        assert alias["entries"] == [{"type": "host", "value": host, "raw": f"host {host}"}]
    assert all(c["coverage"] == "completed" and c["identityKnown"] for c in controllers.values())
    assert len(snapshot["roles"]) == 4
    assert len({r["id"] for r in snapshot["roles"]}) == 4


def test_identity_survives_display_rename_but_changes_with_port_or_scope():
    first = parsed()
    renamed = parsed(name="new label")
    alternate_port = parsed(port=2222)
    alternate_scope = parsed()
    object.__setattr__(alternate_scope.controller, "scope", "node /md/site")
    ids = [build({}, parsed_controllers=[item])["snapshot"]["controllers"][0]["id"] for item in [first, renamed, alternate_port, alternate_scope]]
    assert ids[0] == ids[1]
    assert len({ids[0], ids[2], ids[3]}) == 3


def test_full_binding_rule_raw_and_duplicate_occurrences_are_preserved():
    item = parsed()
    item.role_policies["staff"].rules *= 2
    snapshot = build({}, parsed_controllers=[item], collection_results=[successful(item)])["snapshot"]
    role = next(r for r in snapshot["roles"] if r["name"] == "staff")
    assert role["aclOrder"] == ["first", "staff"]
    assert role["bindingRaw"] == ["session-acl first", "access-list session staff position 20"]
    assert role["observedUsers"] == 3
    assert role["ssids"] == ["wifi-192.0.2.1"]
    assert role["roleTypes"] == ["default"]
    assert role["contextComplete"] is True
    assert [r["ordinal"] for r in snapshot["rules"]] == [1, 2]
    assert len({r["id"] for r in snapshot["rules"]}) == 2
    assert all(r["raw"] == "user alias servers any permit log" and r["sequence"] == "10" for r in snapshot["rules"])


@pytest.mark.parametrize("extra,coverage", [([], "unknown"), ([CommandOutput("rights::staff", "show rights", success=False, error="secret error")], "partial")])
def test_unknown_and_partial_evidence_never_claim_complete_context(extra, coverage):
    item = parsed()
    results = [successful(item, *extra)] if extra else None
    snapshot = build({}, parsed_controllers=[item], collection_results=results)["snapshot"]
    assert snapshot["controllers"][0]["coverage"] == coverage
    assert snapshot["controllers"][0]["failedCommands"] == (["rights::staff"] if extra else [])
    assert not next(r for r in snapshot["roles"] if r["name"] == "staff")["contextComplete"]


def test_named_services_are_explicitly_unknown_without_service_definitions():
    item = parsed(service="svc-custom")
    snapshot = build({}, parsed_controllers=[item], collection_results=[successful(item)])["snapshot"]
    role = next(r for r in snapshot["roles"] if r["name"] == "staff")
    assert role["contextComplete"] is False
    assert snapshot["rules"][0]["service"] == "svc-custom"
    assert any(issue["roleId"] == role["id"] and "서비스" in issue["message"] for issue in snapshot["issues"])


def test_frame_fallback_is_unknown_and_does_not_serialize_private_columns():
    frames = {
        "Role_ACL_Detail": pd.DataFrame([{"controller": "old", "role": "staff", "acl": "staff", "sequence": 1, "raw_rule": "any any any deny log", "source": "any", "destination": "any", "service": "any", "password": "SECRET"}]),
        "Raw_Commands": pd.DataFrame([{"controller": "old", "command_id": "user_table", "output": "PRIVATE_USERS", "error": "SECRET_ERROR", "success": True}]),
        "Role_Network_Context": pd.DataFrame([{"controller": "old", "role": "staff", "observed_user_count": 2, "local_role_networks": "SECRET_NETWORK"}]),
    }
    project = build(frames, collected_at="2026-11-16T00:00:00+00:00")
    controller = project["snapshot"]["controllers"][0]
    assert controller["identityKnown"] is False
    assert controller["host"] == ""
    assert controller["coverage"] == "unknown"
    assert project["snapshot"]["localNetworks"] == []
    serialized = json.dumps(project, allow_nan=False)
    assert all(secret not in serialized for secret in ["SECRET", "PRIVATE_USERS"])
    assert project["createdAt"] == project["updatedAt"] == project["snapshot"]["collectedAt"] == "2026-11-16T00:00:00+00:00"
    assert project["format"] == "aruba-policy-annotations"
    assert project["schemaVersion"] == 1
    assert project["annotations"] == {"roles": {}, "rules": {}}


def test_only_explicit_local_network_frame_is_exported_with_scoped_references():
    item = parsed()
    rows = [{"controller": "same", "role": "staff", "local_role_network": "10.0.0.0/24", "subnet_mask": "255.255.255.0", "status": "Matched", "notes": "local note", "source_file": "PRIVATE_PATH"}]
    project = build({"Local_Role_Networks": pd.DataFrame(rows)}, parsed_controllers=[item])
    local = project["snapshot"]["localNetworks"][0]
    assert local["network"] == "10.0.0.0/24"
    assert local["roleId"] == next(r["id"] for r in project["snapshot"]["roles"] if r["name"] == "staff")
    assert "PRIVATE_PATH" not in json.dumps(project)


@pytest.mark.parametrize("from_frames", [True, False])
def test_ip_catalogue_projects_scoped_references_without_implying_a_role_assignment(from_frames):
    from wlc_role_acl_collector.controller_identity import controller_identity
    from wlc_role_acl_collector.models import RoleNetworkContext, RoleNetworkDefinition
    from wlc_role_acl_collector.report import _build_frames

    item, other = parsed("192.0.2.10"), parsed("198.51.100.10")
    definition = RoleNetworkDefinition("", "192.0.2.0/24", "255.255.255.0", description="project label")
    for controller, subnet in [(item, "192.0.2.0/25"), (other, "198.51.100.0/25")]:
        controller.role_network_contexts = [RoleNetworkContext("same", "staff", "42", subnet, "vlan 42",
            configured_subnet=subnet, observed_networks=["192.0.2.0/24"] if controller is item else [])]
        controller.role_policies["staff"].rules[0].source = "host " + controller.controller.host

    def make(include):
        frames = _build_frames([item, other], [], [definition], export_local_role_networks=include)
        return build(frames, parsed_controllers=None if from_frames else [item, other])["snapshot"]

    snapshot = make(True)
    first_id = next(c["id"] for c in snapshot["controllers"] if c["id"] == controller_identity(item.controller))
    for role in snapshot["roles"]:
        if role["controllerId"] == first_id and role["name"] == "staff":
            assert role["networkReferences"] == [
                "WLC 설정 대역 192.0.2.0/25 → 192.0.2.0/24 · project label",
                "단말 관측 추정 대역 192.0.2.0/24 → 192.0.2.0/24 · project label",
            ]
        else:
            assert "networkReferences" not in role
    assert snapshot["localNetworks"] == []
    for rule in snapshot["rules"]:
        assert rule.get("sourceNetworkReference") == ("192.0.2.0/24 · project label" if rule["controllerId"] == first_id else None)
        assert "destinationNetworkReference" not in rule
    for alias in snapshot["aliases"]:
        assert alias["entries"][0].get("networkReference") == ("192.0.2.0/24 · project label" if alias["controllerId"] == first_id else None)
    private = json.dumps(make(False))
    assert "project label" not in private and "etworkReference" not in private


def test_timestamps_are_timezone_aware_and_invalid_naive_timestamps_fail():
    value = build({}, collected_at=datetime(2026, 11, 16, tzinfo=timezone.utc))
    assert datetime.fromisoformat(value["createdAt"]).tzinfo is not None
    with pytest.raises(ValueError, match="timezone"):
        build({}, collected_at="2026-11-16T00:00:00")


def test_failed_required_collection_is_not_confused_with_another_named_controller():
    first, second = parsed(), parsed("192.0.2.2")
    failed = CollectionResult(first.controller, [CommandOutput("configuration_effective", "show configuration effective", success=False)])
    snapshot = build({}, parsed_controllers=[first, second], collection_results=[successful(second), failed])["snapshot"]
    assert {c["host"]: c["coverage"] for c in snapshot["controllers"]} == {"192.0.2.1": "failed", "192.0.2.2": "completed"}


def test_unresolved_policy_evidence_marks_context_incomplete_and_omits_unknown_fields():
    item = parsed()
    item.unresolved = [{"type": "missing_acl", "name": "first", "context": "role=staff", "credentials": "DO_NOT_INCLUDE"}]
    snapshot = build({}, parsed_controllers=[item], collection_results=[successful(item)])["snapshot"]
    role = next(r for r in snapshot["roles"] if r["name"] == "staff")
    assert role["contextComplete"] is False
    assert snapshot["issues"] == [{"controllerId": role["controllerId"], "roleId": role["id"], "message": "missing_acl: first: role=staff"}]
    assert "DO_NOT_INCLUDE" not in json.dumps(snapshot)


def test_ambiguous_local_network_rows_are_omitted_until_explicitly_scoped():
    from wlc_role_acl_collector.annotation_project import controller_identity

    first, second = parsed(), parsed("192.0.2.2")
    row = {"controller": "same", "role": "staff", "local_role_network": "10.0.0.0/24"}
    ambiguous = build({"Local_Role_Networks": pd.DataFrame([row])}, parsed_controllers=[first, second])["snapshot"]
    assert ambiguous["localNetworks"] == []
    assert len(ambiguous["issues"]) == 2
    row["controller_id"] = controller_identity(second.controller)
    scoped = build({"Local_Role_Networks": pd.DataFrame([row])}, parsed_controllers=[first, second])["snapshot"]
    assert len(scoped["localNetworks"]) == 1
    assert scoped["localNetworks"][0]["controllerId"] == row["controller_id"]


def test_sparse_legacy_frames_preserve_roles_without_rules_and_alias_empty_membership():
    frames = {
        "Role_ACL_Detail": pd.DataFrame([{"controller": "old", "role": "empty", "acl": "staff", "raw_rule": float("nan")}, {"controller": "old", "role": "staff", "acl": "staff", "raw_rule": "any any any deny", "sequence": 1}]),
        "Alias_Detail": pd.DataFrame([{"controller": "old", "alias": "unresolved"}]),
    }
    snapshot = build(frames)["snapshot"]
    assert [r["name"] for r in snapshot["roles"]] == ["empty", "staff"]
    assert len(snapshot["rules"]) == 1
    assert snapshot["aliases"][0]["entries"] == []
    json.dumps(snapshot, allow_nan=False)


def test_local_only_roles_remain_scoped_and_explicitly_incomplete():
    item = parsed()
    snapshot = build({"Local_Role_Networks": pd.DataFrame([{"controller": "same", "role": "local-only", "local_role_network": "10.0.0.0/24"}])}, parsed_controllers=[item])["snapshot"]
    role = next(r for r in snapshot["roles"] if r["name"] == "local-only")
    assert role["contextComplete"] is False
    assert snapshot["localNetworks"][0]["roleId"] == role["id"]


def test_explicit_frame_controller_ids_isolate_legacy_records_without_claiming_identity():
    rows = [{"controller": "same", "controller_id": f"frame-{index}", "role": "staff", "acl": "staff", "raw_rule": f"rule {index}", "service": "any"} for index in [1, 2]]
    snapshot = build({"Role_ACL_Detail": pd.DataFrame(rows)})["snapshot"]
    assert len(snapshot["controllers"]) == 2
    assert all(c["identityKnown"] is False for c in snapshot["controllers"])
    assert len({r["roleId"] for r in snapshot["rules"]}) == 2

"""Build the allowlisted, credential-free offline annotation project snapshot.

Parsed objects are authoritative when supplied: report frames have historically
identified controllers by display name, which cannot isolate identically named
devices. Legacy frames therefore carry explicitly unknown endpoint identity.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .collection_health import assess_collection_results
from .controller_identity import controller_identity, controller_scope as _scope, stable_id as _id
from .models import CollectionResult, ParsedController


def build_annotation_project(
    frames: Mapping[str, Any],
    *,
    parsed_controllers: Iterable[ParsedController] | None = None,
    collection_results: Iterable[CollectionResult] | None = None,
    collected_at: str | datetime | None = None,
) -> dict[str, Any]:
    """Create schemaVersion 1 without serializing arbitrary dataclass/frame fields.

    ``Local_Role_Networks`` is the sole opt-in source of local network exports.
    Unknown/partial coverage and unsupported service semantics remain explicit;
    no absence in this snapshot proves that a prior policy was deleted.
    """
    timestamp = _timestamp(collected_at)
    snapshot_id = f"snapshot-{uuid.uuid4().hex}"
    snapshot: dict[str, Any] = {
        "id": snapshot_id, "collectedAt": timestamp, "controllers": [],
        "roles": [], "rules": [], "aliases": [], "localNetworks": [], "issues": [],
    }
    results = list(collection_results or [])
    if parsed_controllers is not None:
        seen: set[str] = set()
        for parsed in parsed_controllers:
            controller = parsed.controller
            known = bool(controller.host.strip())
            cid = controller_identity(controller) if known else _id("controller", snapshot_id, len(seen), controller.name)
            if cid in seen:
                raise ValueError("Duplicate controller endpoint, port and configuration scope")
            seen.add(cid)
            matching = [r for r in results if controller_identity(r.controller) == controller_identity(controller)] if known else []
            health = assess_collection_results(matching) if matching else None
            controller_row = {
                "id": cid, "name": controller.name, "host": controller.host if known else "",
                "port": int(controller.port) if known else 0, "scope": _scope(controller),
                "identityKnown": known, "coverage": health.status if health else "unknown",
                "failedCommands": list(dict.fromkeys(health.failed_command_ids)) if health else [],
            }
            snapshot["controllers"].append(controller_row)
            _from_parsed(snapshot, parsed, controller_row)
    else:
        _from_frames(snapshot, frames)
    _local_networks(snapshot, _rows(frames, "Local_Role_Networks"))
    if "Local_Role_Networks" in frames:
        _network_references(snapshot, frames)
    return {
        "format": "aruba-policy-annotations", "schemaVersion": 1,
        "projectId": f"project-{uuid.uuid4().hex}", "revision": 0,
        "createdAt": timestamp, "updatedAt": timestamp, "snapshot": snapshot,
        "annotations": {"roles": {}, "rules": {}}, "unresolvedAnnotations": [],
        "changes": [], "importHistory": [],
    }


def _from_parsed(snapshot: dict[str, Any], parsed: ParsedController, controller: dict[str, Any]) -> None:
    cid = controller["id"]
    roles: dict[str, dict[str, Any]] = {}
    names = list(parsed.role_policies)
    for mapping in parsed.ssid_role_mappings:
        if mapping.role and mapping.role not in names:
            names.append(mapping.role)
    for context in parsed.role_network_contexts:
        if context.role and context.role not in names:
            names.append(context.role)
    for name in parsed.user_role_observations:
        if name not in names:
            names.append(name)
    for name in names:
        policy = parsed.role_policies.get(name)
        mappings = [m for m in parsed.ssid_role_mappings if m.role == name]
        observation = parsed.user_role_observations.get(name)
        contexts = [c for c in parsed.role_network_contexts if c.role == name]
        role = _role(cid, name, complete=controller["coverage"] == "completed" and policy is not None)
        role.update({
            "ssids": _unique(m.ssid for m in mappings),
            "roleTypes": _unique(m.role_type for m in mappings),
            "aclOrder": list(policy.acl_names) if policy else [],
            "bindingRaw": [str(line) for line in policy.raw_lines if re.match(r"^\s*(?:session-acl\s|access-list\s+session\s)", line, re.I)] if policy else [],
            "observedUsers": _count(observation.observed_user_count) if observation else max((_count(c.observed_user_count) for c in contexts), default=0),
        })
        roles[name] = role
        snapshot["roles"].append(role)
        for ordinal, rule in enumerate(policy.rules if policy else [], 1):
            _add_rule(snapshot, role, {
                "acl": rule.acl, "sequence": rule.sequence, "raw_rule": rule.raw,
                "source": rule.source, "destination": rule.destination,
                "service": rule.service, "action": rule.action,
            }, ordinal)
    for name, entries in parsed.netdestination_aliases.items():
        snapshot["aliases"].append({
            "id": _id("alias", cid, name), "controllerId": cid, "name": name,
            "entries": [{"type": e.entry_type, "value": e.value, "raw": e.raw} for e in entries],
        })
    for issue in parsed.unresolved:
        context = _text(issue.get("context"))
        role = roles.get(context[5:]) if context.startswith("role=") else None
        message = ": ".join(filter(None, [_text(issue.get("type")), _text(issue.get("name")), context]))
        _issue(snapshot, cid, role["id"] if role else "", message or "정책 문맥을 확인할 수 없습니다.")
        if role:
            role["contextComplete"] = False
        else:
            for candidate in roles.values():
                candidate["contextComplete"] = False


def _from_frames(snapshot: dict[str, Any], frames: Mapping[str, Any]) -> None:
    policy_rows = _rows(frames, "Role_ACL_Detail")
    ssid_rows = _rows(frames, "SSID_Role_Map")
    context_rows = _rows(frames, "Role_Network_Context")
    alias_rows = _rows(frames, "Alias_Detail")
    issue_rows = _rows(frames, "Unresolved")
    all_rows = [*policy_rows, *ssid_rows, *context_rows, *alias_rows, *issue_rows, *_rows(frames, "Overview"), *_rows(frames, "Raw_Commands"), *_rows(frames, "Local_Role_Networks")]
    controllers: dict[str, str] = {}
    for row in all_rows:
        name = _text(row.get("controller"))
        key = _frame_key(row)
        if key not in controllers:
            cid = _text(row.get("controller_id")) or _id("controller", snapshot["id"], name)
            controllers[key] = cid
            commands = [r for r in _rows(frames, "Raw_Commands") if _frame_key(r) == key]
            failed = _unique(_text(r.get("command_id")) for r in commands if not _success(r.get("success")))
            required = next((r for r in commands if _text(r.get("command_id")) == "configuration_effective"), None)
            coverage = "failed" if required and not _success(required.get("success")) else "partial" if failed else "unknown"
            snapshot["controllers"].append({"id": cid, "name": name, "host": "", "port": 0, "scope": "effective", "identityKnown": False, "coverage": coverage, "failedCommands": failed})
    roles: dict[tuple[str, str], dict[str, Any]] = {}
    for row in [*policy_rows, *ssid_rows, *context_rows]:
        key = (_frame_key(row), _text(row.get("role")))
        if key[1] and key not in roles:
            role = _role(controllers[key[0]], key[1], complete=False)
            roles[key] = role
            snapshot["roles"].append(role)
    for key, role in roles.items():
        matching = lambda rows: [r for r in rows if (_frame_key(r), _text(r.get("role"))) == key]
        mappings = matching(ssid_rows)
        role["ssids"] = _unique(_text(r.get("ssid")) for r in mappings)
        role["roleTypes"] = _unique(_text(r.get("role_type")) for r in mappings)
        role["observedUsers"] = max((_count(r.get("observed_user_count")) for r in [*matching(context_rows), *mappings]), default=0)
        ordinal = 0
        for row in matching(policy_rows):
            acl = _text(row.get("acl"))
            if acl and acl not in role["aclOrder"]:
                role["aclOrder"].append(acl)
            if _text(row.get("raw_rule")):
                ordinal += 1
                _add_rule(snapshot, role, row, ordinal)
    aliases: dict[tuple[str, str], dict[str, Any]] = {}
    for row in alias_rows:
        key = (_frame_key(row), _text(row.get("alias")))
        if not key[1]:
            continue
        if key not in aliases:
            cid = controllers[key[0]]
            aliases[key] = {"id": _id("alias", cid, key[1]), "controllerId": cid, "name": key[1], "entries": []}
            snapshot["aliases"].append(aliases[key])
        if any(_text(row.get(k)) for k in ["entry_type", "value", "raw"]):
            aliases[key]["entries"].append({"type": _text(row.get("entry_type")), "value": _text(row.get("value")), "raw": _text(row.get("raw"))})
    for row in issue_rows:
        cid = controllers[_frame_key(row)]
        role = roles.get((_frame_key(row), _text(row.get("role"))))
        _issue(snapshot, cid, role["id"] if role else "", ": ".join(filter(None, [_text(row.get(k)) for k in ["type", "name", "context"]])) or "정책 문맥을 확인할 수 없습니다.")


def _role(cid: str, name: str, *, complete: bool) -> dict[str, Any]:
    return {"id": _id("role", cid, name), "controllerId": cid, "name": name, "ssids": [], "roleTypes": [], "aclOrder": [], "bindingRaw": [], "contextComplete": complete, "observedUsers": 0}


def _add_rule(snapshot: dict[str, Any], role: dict[str, Any], row: Mapping[str, Any], ordinal: int) -> None:
    raw = _text(row.get("raw_rule"))
    rule = {"id": _id("rule", snapshot["id"], role["id"], ordinal, raw), "controllerId": role["controllerId"], "roleId": role["id"], "acl": _text(row.get("acl")), "sequence": _text(row.get("sequence")), "ordinal": ordinal, "raw": raw}
    for key in ["source", "destination", "service", "action"]:
        rule[key] = _text(row.get(key))
    for key in ["source", "destination"]:
        value = rule[key].casefold()
        rule[key + "Interpretation"] = "User IP (current client assigned to this role)" if value == "user" else "Any (0.0.0.0/0)" if value == "any" else ""
    snapshot["rules"].append(rule)
    # Service objects (including familiar svc-* names) are not collected; a
    # service label alone cannot establish its current controller definition.
    if rule["service"].casefold() not in {"any", "ip"}:
        role["contextComplete"] = False
        _issue(snapshot, role["controllerId"], role["id"], f"서비스 정의를 수집하지 않아 의미를 확인할 수 없습니다: {rule['service'] or '(비어 있음)'}")


def _local_networks(snapshot: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    for row in rows:
        explicit_id = _text(row.get("controller_id"))
        candidates = [c for c in snapshot["controllers"] if c["id"] == explicit_id] if explicit_id else [c for c in snapshot["controllers"] if c["name"] == _text(row.get("controller"))]
        if len(candidates) != 1:
            for controller in candidates:
                _issue(snapshot, controller["id"], "", "장비 식별이 모호하여 내부망 대역 항목을 제외했습니다.")
            continue
        cid = candidates[0]["id"]
        role_name = _text(row.get("role"))
        role = next((r for r in snapshot["roles"] if r["controllerId"] == cid and r["name"] == role_name), None)
        if role is None and role_name:
            role = _role(cid, role_name, complete=False)
            snapshot["roles"].append(role)
        if role is None:
            continue
        snapshot["localNetworks"].append({"controllerId": cid, "roleId": role["id"], "network": _text(row.get("local_role_network")), "subnetMask": _text(row.get("subnet_mask")), "status": _text(row.get("status")), "notes": _text(row.get("notes"))})


def _network_references(snapshot: dict[str, Any], frames: Mapping[str, Any]) -> None:
    """Copy only references resolved in this opt-in report and tied to its source records."""
    roles = {(r["controllerId"], r["name"]): r for r in snapshot["roles"]}
    for row in _rows(frames, "Role_Network_Context"):
        role = roles.get((_text(row.get("controller_id")), _text(row.get("role"))))
        lines = _text(row.get("network_references")).splitlines()
        if role is not None and lines:
            role["networkReferences"] = _unique([*role.get("networkReferences", []), *lines])

    # The same operand may occur in many rules within a controller.
    operands: dict[tuple[str, str], str] = {}
    for row in _rows(frames, "Role_ACL_Detail"):
        for field in ("source", "destination"):
            reference = _text(row.get(field + "_network_reference"))
            if reference:
                operands[(_text(row.get("controller_id")), _text(row.get(field)))] = reference
    for rule in snapshot["rules"]:
        for field in ("source", "destination"):
            reference = operands.get((rule["controllerId"], rule[field]))
            if reference:
                rule[field + "NetworkReference"] = reference

    entries = {
        (_text(row.get("controller_id")), _text(row.get("alias")), _text(row.get("entry_type")), _text(row.get("value"))): reference
        for row in _rows(frames, "Alias_Detail")
        if (reference := _text(row.get("network_reference")))
    }
    for alias in snapshot["aliases"]:
        for entry in alias["entries"]:
            reference = entries.get((alias["controllerId"], alias["name"], entry["type"], entry["value"]))
            if reference:
                entry["networkReference"] = reference


def _issue(snapshot: dict[str, Any], cid: str, rid: str, message: str) -> None:
    value = {"controllerId": cid, "roleId": rid, "message": message}
    if value not in snapshot["issues"]:
        snapshot["issues"].append(value)


def _rows(frames: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    frame = frames.get(key)
    if frame is None:
        return []
    return frame.to_dict(orient="records") if hasattr(frame, "to_dict") else list(frame)


def _text(value: Any) -> str:
    if value is None or isinstance(value, float) and math.isnan(value):
        return ""
    return str(value)


def _frame_key(row: Mapping[str, Any]) -> str:
    return _text(row.get("controller_id")) or _text(row.get("controller"))


def _count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _success(value: Any) -> bool:
    return _text(value).strip().casefold() in {"true", "1", "yes", "y"}


def _timestamp(value: str | datetime | None) -> str:
    parsed = datetime.now(timezone.utc) if value is None else datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("collected_at must include a timezone")
    return parsed.isoformat(timespec="seconds")

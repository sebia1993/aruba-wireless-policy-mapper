"""Stable identities shared by annotation snapshots and collection summaries."""

from __future__ import annotations

import hashlib
import json
import math

from .models import Controller


def stable_id(kind: str, *parts: object) -> str:
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return f"{kind}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]}"


def controller_scope(controller: Controller) -> str:
    value = getattr(controller, "scope", getattr(controller, "configuration_scope", "effective"))
    if value is None or isinstance(value, float) and math.isnan(value):
        return "effective"
    return str(value) or "effective"


def controller_identity(controller: Controller) -> str:
    """Return the existing endpoint/port/scope identity, ignoring display name."""
    host = controller.host.strip().casefold().rstrip(".")
    return stable_id("controller", host, int(controller.port), controller_scope(controller))

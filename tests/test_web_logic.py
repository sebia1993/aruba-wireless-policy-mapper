from io import BytesIO
from pathlib import Path
import threading

from openpyxl import Workbook
import pytest

import wlc_role_acl_collector.web_logic as web_logic
from wlc_role_acl_collector.collector import collect_from_offline_raw
from wlc_role_acl_collector.models import CommandOutput, Controller
from wlc_role_acl_collector.web_logic import (
    WebCollectionBusyError,
    WebCollectionRequest,
    run_web_collection,
)


def test_run_web_collection_offline_returns_preview_and_downloads():
    fixture_root = Path(__file__).parent / "fixtures"
    role_networks = _role_network_workbook_bytes()
    events = []

    result = run_web_collection(
        WebCollectionRequest(
            host="192.0.2.10",
            controller_name="sample_controller",
            username="",
            password="",
            role_networks_filename="role_networks.xlsx",
            role_networks_bytes=role_networks,
            offline_raw_dir=fixture_root,
        ),
        progress_callback=lambda event, payload: events.append((event, payload)),
    )

    assert result.success is True
    assert result.summary["ssid_count"] > 0
    assert result.summary["role_network_rows"] == 1
    assert result.preview_rows
    assert result.acl_preview_rows
    assert {"xlsx", "csv", "html"}.issubset(result.artifacts)
    assert result.artifacts["xlsx"].filename.endswith(".xlsx")
    assert result.artifacts["csv"].data.startswith(b"\xef\xbb\xbfcontroller,ssid")
    assert b"guest-logon" in result.artifacts["csv"].data
    assert result.artifacts["html"].data.startswith(b"<!doctype html>")
    assert any(event == "complete" for event, _payload in events)


def test_run_web_collection_rejects_concurrent_collection_for_same_wlc(monkeypatch):
    fixture_root = Path(__file__).parent / "fixtures"
    request = WebCollectionRequest(
        host="192.0.2.10",
        controller_name="sample_controller",
        username="",
        password="",
        offline_raw_dir=fixture_root,
    )
    entered = threading.Event()
    release = threading.Event()
    original_collect = web_logic._collect

    def blocking_collect(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return original_collect(*args, **kwargs)

    monkeypatch.setattr(web_logic, "_collect", blocking_collect)
    result_holder = {}

    def first_collection():
        result_holder["result"] = run_web_collection(request)

    worker = threading.Thread(target=first_collection)
    worker.start()
    assert entered.wait(timeout=5)
    try:
        with pytest.raises(WebCollectionBusyError, match="이미 수집"):
            run_web_collection(request)
    finally:
        release.set()
        worker.join(timeout=10)

    assert not worker.is_alive()
    assert result_holder["result"].success is True


@pytest.mark.parametrize(
    ("collection_request", "message"),
    [
        (
            WebCollectionRequest(host="https://192.0.2.10", username="admin", password="secret"),
            "URL이나 경로",
        ),
        (
            WebCollectionRequest(host="192.0.2.10", username="admin", password="secret", timeout=601),
            "5에서 600",
        ),
    ],
)
def test_run_web_collection_rejects_invalid_address_and_timeout(collection_request, message):
    with pytest.raises(ValueError, match=message):
        run_web_collection(collection_request)


def test_web_summary_includes_affected_role_and_ssid_for_partial_collection(monkeypatch):
    fixture_root = Path(__file__).parent / "fixtures"
    result = collect_from_offline_raw(
        Controller(name="sample_controller", host="192.0.2.10"),
        fixture_root,
    )
    result.commands.append(
        CommandOutput(
            command_id="rights::corp-employee",
            command="show rights corp-employee",
            success=False,
            error="command timed out",
        )
    )
    monkeypatch.setattr(web_logic, "_collect", lambda *_args, **_kwargs: result)

    web_result = run_web_collection(
        WebCollectionRequest(
            host="192.0.2.10",
            controller_name="sample_controller",
            username="admin",
            password="secret",
        )
    )

    assert web_result.success is True
    assert web_result.summary["collection_status"] == "partial"
    assert web_result.summary["affected_role_count"] == 1
    assert web_result.summary["affected_roles"] == "corp-employee"
    assert web_result.summary["affected_ssid_count"] == 1
    assert web_result.summary["affected_ssids"] == "CORP"


def _role_network_workbook_bytes() -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Role_Networks"
    worksheet.append(["Role 이름", "네트워크 대역", "서브넷마스크"])
    worksheet.append(["guest-logon", "10.30.0.0/24", ""])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()

from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from wlc_role_acl_collector.role_networks import (
    ROLE_NETWORKS_FALLBACK_NOTICE,
    RoleNetworkDefinitionError,
    load_role_network_definitions,
    load_role_network_definitions_with_summary,
)


def test_role_network_header_is_validated_before_consuming_data(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from wlc_role_acl_collector import role_networks

    source = tmp_path / "header.xlsx"
    _write_workbook(source, [["wrong column"]])
    closed = []

    def rows(**kwargs):
        yield ("wrong column",)
        raise AssertionError("read data before rejecting the invalid header")

    worksheet = SimpleNamespace(title="Sheet", iter_rows=rows)
    workbook = SimpleNamespace(sheetnames=["Sheet"], worksheets=[worksheet], close=lambda: closed.append(True))
    monkeypatch.setattr(role_networks, "load_workbook", lambda *_args, **_kwargs: workbook)

    with pytest.raises(RoleNetworkDefinitionError, match="missing required column"):
        load_role_network_definitions(source)
    assert closed == [True]


def test_role_network_rows_are_processed_before_reading_the_next_row(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from wlc_role_acl_collector import role_networks

    source = tmp_path / "stream.xlsx"
    _write_workbook(source, [["Role", "Network"], ["sample", "192.0.2.0/24"]])
    parsed = []
    real_normalize = role_networks._normalize_network

    def normalize(network, mask):
        parsed.append(network)
        return real_normalize(network, mask)

    def rows(**kwargs):
        yield ("Role", "Network")
        yield ("first", "192.0.2.0/24")
        assert parsed == ["192.0.2.0/24"], "mapping rows were buffered instead of processed"
        yield ("second", "198.51.100.0/24")

    worksheet = SimpleNamespace(title="Sheet", iter_rows=rows)
    workbook = SimpleNamespace(sheetnames=["Sheet"], worksheets=[worksheet], close=lambda: None)
    monkeypatch.setattr(role_networks, "load_workbook", lambda *_args, **_kwargs: workbook)
    monkeypatch.setattr(role_networks, "_normalize_network", normalize)

    result = load_role_network_definitions_with_summary(source)
    assert [(item.role, item.network, item.source_row) for item in result.definitions] == [
        ("first", "192.0.2.0/24", 2), ("second", "198.51.100.0/24", 3)
    ]


def test_load_role_network_definitions_normalizes_korean_template(tmp_path):
    path = tmp_path / "role_networks.xlsx"
    _write_workbook(
        path,
        [
            ["Role 이름", "네트워크 대역", "서브넷마스크"],
            ["guest-logon", "10.30.0.5", "255.255.255.0"],
            ["corp-employee", "10.40.1.0/24", ""],
            ["guest-logon", "10.31.0.0", "255.255.0.0"],
        ],
    )

    definitions = load_role_network_definitions(path)

    assert [(item.role, item.network, item.subnet_mask, item.source_row) for item in definitions] == [
        ("guest-logon", "10.30.0.0/24", "255.255.255.0", 2),
        ("corp-employee", "10.40.1.0/24", "255.255.255.0", 3),
        ("guest-logon", "10.31.0.0/16", "255.255.0.0", 4),
    ]


def test_load_role_network_summary_counts_roles_networks_and_duplicates(tmp_path):
    path = tmp_path / "role_networks.xlsx"
    _write_workbook(
        path,
        [
            ["Role 이름", "네트워크 대역", "서브넷마스크"],
            ["guest-logon", "10.30.0.0/24", ""],
            ["guest-logon", "10.30.0.0/24", ""],
            ["corp-employee", "10.40.1.0/24", ""],
        ],
    )

    summary = load_role_network_definitions_with_summary(path)

    assert summary.role_count == 2
    assert summary.network_count == 2
    assert summary.duplicate_count == 1
    assert summary.source_file == str(path)
    assert [(item.role, item.network) for item in summary.definitions] == [
        ("guest-logon", "10.30.0.0/24"),
        ("corp-employee", "10.40.1.0/24"),
    ]


@pytest.mark.parametrize("with_role", [True, False])
def test_network_reference_rows_allow_omitted_role_and_keep_distinct_descriptions(tmp_path, with_role):
    path = tmp_path / "ranges.xlsx"
    headers = ["네트워크 대역", "설명"]
    rows = [["192.0.2.0/24", title] for title in ["사내망", "사내망", "업무망"]]
    if with_role:
        headers.append("Role 이름")
    _write_workbook(path, [headers, *rows])
    result = load_role_network_definitions_with_summary(path)
    assert result.role_count == 0
    assert result.duplicate_count == 1
    assert [(d.role, d.description) for d in result.definitions] == [("", "사내망"), ("", "업무망")]


def test_load_role_network_definitions_allows_cidr_without_subnet_mask_column(tmp_path):
    path = tmp_path / "role_networks.xlsx"
    _write_workbook(
        path,
        [
            ["Role 이름", "네트워크 대역"],
            ["guest-logon", "10.30.0.0/24"],
            ["corp-employee", "10.40.1.0/24"],
        ],
    )

    definitions = load_role_network_definitions(path)

    assert [(item.role, item.network, item.subnet_mask) for item in definitions] == [
        ("guest-logon", "10.30.0.0/24", "255.255.255.0"),
        ("corp-employee", "10.40.1.0/24", "255.255.255.0"),
    ]


def test_network_reference_most_specific_whole_operand_and_tied_descriptions():
    from wlc_role_acl_collector.models import RoleNetworkDefinition
    from wlc_role_acl_collector.role_networks import NetworkReferenceIndex

    index = NetworkReferenceIndex([
        RoleNetworkDefinition("", cidr, "", description=label)
        for cidr, label in [
            ("192.0.2.0/24", "상위망"), ("192.0.2.128/25", "직원망"),
            ("192.0.2.128/25", "업무망"), ("192.0.2.128/25", "직원망"),
            ("0.0.0.0/1", ""),
        ]
    ])
    for operand in ("host 192.0.2.160", "192.0.2.160", "network 192.0.2.161 255.255.255.224",
                    "network 192.0.2.161/27", "host 192.0.2.159/32", "range 192.0.2.159 - 192.0.2.180"):
        assert index.lookup(operand) == "192.0.2.128/25 · 직원망 / 업무망"
    assert index.lookup("range 192.0.2.110 192.0.2.160") == "192.0.2.0/24 · 상위망"
    assert index.lookup("host 192.0.2.132/24") == "192.0.2.0/24 · 상위망"
    assert index.lookup("10.0.0.8") == "0.0.0.0/1"
    for operand in ("192.0.2.0/23", "range 192.0.1.255 192.0.2.2", "range 192.0.2.5 192.0.2.1",
                    "any", "user", "alias staff", "name 192.0.2.132",
                    "host example.org", "network 192.0.2.132 garbage", "2001:db8::1"):
        assert index.lookup(operand) == ""


def test_packaged_role_network_template_contains_input_and_guide_sheets():
    path = Path(__file__).parents[1] / "config" / "role_networks.example.xlsx"
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        assert workbook.sheetnames[:2] == ["Role_Networks", "작성가이드"]
        input_rows = list(workbook["Role_Networks"].iter_rows(values_only=True))
        guide_text = "\n".join(
            str(value)
            for row in workbook["작성가이드"].iter_rows(values_only=True)
            for value in row
            if value
        )
    finally:
        workbook.close()

    assert input_rows[0][:2] == ("Role 이름", "네트워크 대역")
    assert ("corp-employee", "10.40.2.0/24") == input_rows[3][:2]
    assert "같은 Role에 여러 대역" in guide_text
    assert "내부망 전용" in guide_text
    assert "Role_Networks Sheet가 있으면" in guide_text

    definitions = load_role_network_definitions(path)
    assert [(item.role, item.network) for item in definitions] == [
        ("guest-logon", "10.30.0.0/24"),
        ("corp-employee", "10.40.1.0/24"),
        ("corp-employee", "10.40.2.0/24"),
    ]


def test_load_role_network_definitions_prefers_role_networks_sheet_even_when_second(tmp_path):
    path = tmp_path / "role_networks.xlsx"
    _write_multi_sheet_workbook(
        path,
        [
            (
                "사내대역",
                [
                    ["Role 이름", "네트워크 대역"],
                    ["wrong-first-sheet", "192.0.2.0/24"],
                ],
            ),
            (
                "Role_Networks",
                [
                    ["Role 이름", "네트워크 대역"],
                    ["guest-logon", "10.30.0.0/24"],
                    ["corp-employee", "10.40.1.0/24"],
                ],
            ),
        ],
    )

    summary = load_role_network_definitions_with_summary(path)

    assert summary.sheet_name == "Role_Networks"
    assert summary.sheet_fallback_used is False
    assert summary.sheet_notice == ""
    assert [(item.role, item.network, item.source_row) for item in summary.definitions] == [
        ("guest-logon", "10.30.0.0/24", 2),
        ("corp-employee", "10.40.1.0/24", 3),
    ]


def test_load_role_network_definitions_skips_guide_sheet_when_role_networks_is_second(tmp_path):
    path = tmp_path / "role_networks.xlsx"
    _write_multi_sheet_workbook(
        path,
        [
            ("작성가이드", [["이 시트는 설명용입니다."], ["Role 이름", "네트워크 대역"], ["wrong", "192.0.2.0/24"]]),
            (
                "Role_Networks",
                [
                    ["Role 이름", "네트워크 대역"],
                    ["corp-employee", "10.40.1.0/24"],
                ],
            ),
        ],
    )

    summary = load_role_network_definitions_with_summary(path)

    assert summary.sheet_name == "Role_Networks"
    assert summary.sheet_fallback_used is False
    assert [(item.role, item.network) for item in summary.definitions] == [
        ("corp-employee", "10.40.1.0/24"),
    ]


def test_load_role_network_definitions_falls_back_to_first_sheet_without_role_networks(tmp_path):
    path = tmp_path / "role_networks.xlsx"
    _write_multi_sheet_workbook(
        path,
        [
            (
                "사내대역",
                [
                    ["Role 이름", "네트워크 대역"],
                    ["guest-logon", "10.30.0.0/24"],
                ],
            ),
            ("작성가이드", [["이 시트는 설명용입니다."]]),
        ],
    )

    summary = load_role_network_definitions_with_summary(path)

    assert summary.sheet_name == "사내대역"
    assert summary.sheet_fallback_used is True
    assert summary.sheet_notice == ROLE_NETWORKS_FALLBACK_NOTICE
    assert [(item.role, item.network) for item in summary.definitions] == [("guest-logon", "10.30.0.0/24")]


def test_load_role_network_definitions_rejects_invalid_rows(tmp_path):
    path = tmp_path / "role_networks.xlsx"
    _write_workbook(
        path,
        [
            ["role", "network", "subnet_mask"],
            ["guest-logon", "10.30.0.0", ""],
            ["corp-employee", "10.40.1.0/24", "255.255.0.0"],
        ],
    )

    with pytest.raises(RoleNetworkDefinitionError) as exc_info:
        load_role_network_definitions(path)

    message = str(exc_info.value)
    assert "Subnet mask is required" in message
    assert "CIDR prefix and subnet mask do not match" in message


def test_load_role_network_definitions_rejects_renamed_text_file(tmp_path):
    path = tmp_path / "role_networks.xlsx"
    path.write_text("role,network,subnet_mask\ncorp,10.10.10.0,255.255.255.0\n", encoding="utf-8")

    with pytest.raises(RoleNetworkDefinitionError) as exc_info:
        load_role_network_definitions(path)

    message = str(exc_info.value)
    assert "not a valid Excel xlsx/xlsm workbook" in message
    assert "Do not rename a CSV, HTML, or .xls file to .xlsx" in message


def test_load_role_network_definitions_rejects_excel_lock_file(tmp_path):
    path = tmp_path / "~$role_networks.xlsx"
    path.write_bytes(b"")

    with pytest.raises(RoleNetworkDefinitionError) as exc_info:
        load_role_network_definitions(path)

    assert "temporary lock file" in str(exc_info.value)


def test_load_role_network_definitions_rejects_old_xls_file(tmp_path):
    path = tmp_path / "role_networks.xls"
    path.write_bytes(b"old excel bytes")

    with pytest.raises(RoleNetworkDefinitionError) as exc_info:
        load_role_network_definitions(path)

    message = str(exc_info.value)
    assert "old .xls workbook" in message
    assert "save it as Excel Workbook (*.xlsx)" in message


def _write_workbook(path: Path, rows: list[list[str]]) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    for row in rows:
        worksheet.append(row)
    workbook.save(path)


def _write_multi_sheet_workbook(path: Path, sheets: list[tuple[str, list[list[str]]]]) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, rows in sheets:
        worksheet = workbook.create_sheet(title)
        for row in rows:
            worksheet.append(row)
    workbook.save(path)

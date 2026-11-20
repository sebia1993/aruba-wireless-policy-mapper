"""Load optional local Role-to-network Excel mappings.

These mappings are treated as sensitive internal data. By default they are read
for the current run only and are not exported into generated reports.
"""

from __future__ import annotations

import ipaddress
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from .models import RoleNetworkDefinition


class RoleNetworkDefinitionError(ValueError):
    pass


class NetworkReferenceIndex:
    """Look up a numeric operand in the uploaded IPv4 catalogue, independently of Role."""

    def __init__(self, definitions: list[RoleNetworkDefinition]) -> None:
        descriptions: dict[ipaddress.IPv4Network, dict[str, None]] = {}
        for definition in definitions:
            network = ipaddress.IPv4Network(definition.network, strict=False)
            labels = descriptions.setdefault(network, {})
            if definition.description:
                labels[" ".join(definition.description.splitlines())] = None
        self._by_prefix: dict[int, dict[int, str]] = {}
        for network, labels in descriptions.items():
            text = str(network)
            if labels:
                text += " · " + " / ".join(labels)
            shift = 32 - network.prefixlen
            self._by_prefix.setdefault(shift, {})[int(network.network_address) >> shift] = text
        self._shifts = sorted(self._by_prefix)
        self._cache: dict[str, str] = {}

    def lookup(self, operand: str) -> str:
        if operand not in self._cache:
            self._cache[operand] = self._lookup(operand)
        return self._cache[operand]

    def _lookup(self, operand: str) -> str:
        tokens = operand.lower().split()
        if not tokens or not self._shifts:
            return ""
        kind = tokens[0]
        try:
            if kind == "range":
                bounds = re.fullmatch(r"([\d.]+)(?:\s*-\s*|\s+)([\d.]+)", " ".join(tokens[1:]))
                if bounds is None:
                    return ""
                first, last = (int(ipaddress.IPv4Address(ip)) for ip in bounds.groups())
                if first > last:
                    return ""
            else:
                if kind == "host" and len(tokens) == 2:
                    cidr = tokens[1]  # show netdestination also emits host <address>/32.
                elif kind == "network" and len(tokens) in (2, 3):
                    cidr = "/".join(tokens[1:])
                elif len(tokens) == 1:
                    cidr = tokens[0]
                else:
                    return ""
                subnet = ipaddress.IPv4Network(cidr, strict=False)
                first, last = int(subnet.network_address), int(subnet.broadcast_address)
        except ValueError:
            return ""
        for shift in self._shifts:
            prefix = first >> shift
            if prefix == last >> shift:
                match = self._by_prefix[shift].get(prefix)
                if match:
                    return match
        return ""

    def role_references(self, configured: str, observed: list[str]) -> list[str]:
        lines = []
        for evidence, subnets in (("WLC 설정 대역", [configured]), ("단말 관측 추정 대역", observed)):
            for subnet in dict.fromkeys(subnets):
                reference = self.lookup(subnet)
                if reference:
                    lines.append(f"{evidence} {subnet} → {reference}")
        return lines


@dataclass(frozen=True)
class RoleNetworkLoadSummary:
    definitions: list[RoleNetworkDefinition]
    role_count: int
    network_count: int
    duplicate_count: int
    source_file: str
    sheet_name: str = ""
    sheet_fallback_used: bool = False
    sheet_notice: str = ""


ROLE_NETWORKS_SHEET_NAME = "Role_Networks"
ROLE_NETWORKS_FALLBACK_NOTICE = "Role_Networks Sheet가 없어 첫 번째 Sheet를 읽었다."
_EXCEL_FORMAT_HINT = (
    "Use config\\role_networks.example.xlsx as the template, edit only the rows, "
    "then save it as Excel Workbook (*.xlsx). Do not rename a CSV, HTML, or .xls file to .xlsx."
)


_HEADER_ALIASES = {
    "description": {"설명", "대역 설명", "description", "network description"},
    "role": {
        "role",
        "rolename",
        "role name",
        "role이름",
        "role 이름",
        "역할",
        "정책이름",
        "정책 이름",
    },
    "network": {
        "network",
        "networkaddress",
        "network address",
        "networkcidr",
        "network cidr",
        "cidr",
        "subnet",
        "네트워크대역",
        "네트워크 대역",
        "대역",
    },
    "subnet_mask": {
        "subnetmask",
        "subnet mask",
        "netmask",
        "mask",
        "서브넷마스크",
        "서브넷 마스크",
    },
}


def load_role_network_definitions(path: Path | str | None) -> list[RoleNetworkDefinition]:
    return load_role_network_definitions_with_summary(path).definitions


def load_role_network_definitions_with_summary(path: Path | str | None) -> RoleNetworkLoadSummary:
    if path is None:
        return RoleNetworkLoadSummary([], role_count=0, network_count=0, duplicate_count=0, source_file="")

    source = Path(path)
    _validate_excel_file(source)

    try:
        workbook = load_workbook(source, read_only=True, data_only=True)
    except zipfile.BadZipFile as exc:
        raise RoleNetworkDefinitionError(_not_real_xlsx_message(source)) from exc
    except Exception as exc:
        raise RoleNetworkDefinitionError(
            f"Unable to open Role network Excel file: {exc}. {_EXCEL_FORMAT_HINT}"
        ) from exc

    try:
        worksheet, fallback_used = _select_role_network_worksheet(workbook)
        return _load_role_network_worksheet(worksheet, source=source, fallback_used=fallback_used)
    finally:
        workbook.close()


def _load_role_network_worksheet(worksheet, *, source: Path, fallback_used: bool) -> RoleNetworkLoadSummary:
    sheet_name = worksheet.title
    rows = enumerate(worksheet.iter_rows(values_only=True), start=1)
    header = next(((number, row) for number, row in rows if not _row_is_blank(row)), None)
    if header is None:
        raise RoleNetworkDefinitionError("Role network Excel file does not contain a header row.")
    _header_number, header_row = header
    columns = _resolve_columns(header_row)
    errors: list[str] = []
    definitions: list[RoleNetworkDefinition] = []
    seen: set[tuple[str, str, str]] = set()
    duplicate_count = 0

    for row_number, row in rows:
        if _row_is_blank(row):
            continue

        role = _cell_text(_cell_at(row, columns["role"])) if "role" in columns else ""
        description = _cell_text(_cell_at(row, columns["description"])) if "description" in columns else ""
        network_text = _cell_text(_cell_at(row, columns["network"]))
        mask_column = columns.get("subnet_mask")
        mask_text = _cell_text(_cell_at(row, mask_column)) if mask_column is not None else ""

        if not network_text:
            errors.append(f"row {row_number}: Network is required.")
            continue

        try:
            cidr, subnet_mask = _normalize_network(network_text, mask_text)
        except RoleNetworkDefinitionError as exc:
            errors.append(f"row {row_number}: {exc}")
            continue

        dedupe_key = (role.casefold(), cidr, description)
        if dedupe_key in seen:
            duplicate_count += 1
            continue
        seen.add(dedupe_key)
        definitions.append(
            RoleNetworkDefinition(
                role=role,
                network=cidr,
                subnet_mask=subnet_mask,
                source_file=str(source),
                source_row=row_number,
                description=description,
            )
        )

    if errors:
        suffix = "" if len(errors) <= 8 else f" ... and {len(errors) - 8} more error(s)"
        raise RoleNetworkDefinitionError("; ".join(errors[:8]) + suffix)
    if not definitions:
        raise RoleNetworkDefinitionError("Role network Excel file does not contain any mapping rows.")
    return RoleNetworkLoadSummary(
        definitions=definitions,
        role_count=len({definition.role.casefold() for definition in definitions if definition.role}),
        network_count=len(definitions),
        duplicate_count=duplicate_count,
        source_file=str(source),
        sheet_name=sheet_name,
        sheet_fallback_used=fallback_used,
        sheet_notice=ROLE_NETWORKS_FALLBACK_NOTICE if fallback_used else "",
    )


def _select_role_network_worksheet(workbook) -> tuple[Any, bool]:
    if ROLE_NETWORKS_SHEET_NAME in workbook.sheetnames:
        return workbook[ROLE_NETWORKS_SHEET_NAME], False
    return workbook.worksheets[0], True


def _validate_excel_file(source: Path) -> None:
    if not source.exists():
        raise RoleNetworkDefinitionError(f"Role network Excel file was not found: {source}")
    if source.name.startswith("~$"):
        raise RoleNetworkDefinitionError(
            "The selected file looks like an Excel temporary lock file. "
            "Close Excel or select the real workbook file that does not start with '~$'."
        )

    suffix = source.suffix.lower()
    if suffix == ".xls":
        raise RoleNetworkDefinitionError(
            "The selected file is an old .xls workbook. "
            "Open it in Excel and save it as Excel Workbook (*.xlsx), then select the new file."
        )
    if suffix not in {".xlsx", ".xlsm"}:
        raise RoleNetworkDefinitionError(
            f"Role network file must be an .xlsx or .xlsm file. {_EXCEL_FORMAT_HINT}"
        )
    if not zipfile.is_zipfile(source):
        raise RoleNetworkDefinitionError(_not_real_xlsx_message(source))


def _not_real_xlsx_message(source: Path) -> str:
    return (
        f"The selected file is not a valid Excel xlsx/xlsm workbook: {source}. "
        f"{_EXCEL_FORMAT_HINT}"
    )


def _resolve_columns(header_row: tuple[Any, ...]) -> dict[str, int]:
    normalized_headers = {_normalize_header(value): index for index, value in enumerate(header_row)}
    columns: dict[str, int] = {}
    missing: list[str] = []
    for column_name, aliases in _HEADER_ALIASES.items():
        match = next(
            (
                normalized_headers[_normalize_header(alias)]
                for alias in aliases
                if _normalize_header(alias) in normalized_headers
            ),
            None,
        )
        if match is None:
            if column_name == "network":
                missing.append(column_name)
        else:
            columns[column_name] = match
    if missing:
        raise RoleNetworkDefinitionError(
            "Role network Excel file is missing required column(s): " + ", ".join(missing)
        )
    return columns


def _normalize_network(network_text: str, mask_text: str) -> tuple[str, str]:
    try:
        if "/" in network_text:
            network = ipaddress.ip_network(network_text, strict=False)
            if mask_text:
                mask_network = ipaddress.ip_network(f"{network.network_address}/{mask_text}", strict=False)
                if mask_network.prefixlen != network.prefixlen:
                    raise RoleNetworkDefinitionError(
                        f"CIDR prefix and subnet mask do not match for {network_text} / {mask_text}."
                    )
        else:
            if not mask_text:
                raise RoleNetworkDefinitionError(
                    f"Subnet mask is required when network is not CIDR: {network_text}."
                )
            network = ipaddress.ip_network(f"{network_text}/{mask_text}", strict=False)
    except RoleNetworkDefinitionError:
        raise
    except ValueError as exc:
        raise RoleNetworkDefinitionError(f"Invalid network or subnet mask: {network_text} {mask_text}".strip()) from exc

    if network.version != 4:
        raise RoleNetworkDefinitionError(f"Only IPv4 networks are supported: {network_text}.")
    return f"{network.network_address}/{network.prefixlen}", str(network.netmask)


def _normalize_header(value: Any) -> str:
    return re.sub(r"[\s_\-]+", "", _cell_text(value).casefold())


def _cell_at(row: tuple[Any, ...], index: int) -> Any:
    if index >= len(row):
        return ""
    return row[index]


def _row_is_blank(row: tuple[Any, ...]) -> bool:
    return all(not _cell_text(value) for value in row)


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()

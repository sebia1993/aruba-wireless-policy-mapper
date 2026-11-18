"""Validate the Windows release ZIP produced by GitHub Actions.

The checks stay intentionally offline: they inspect the package layout, optional
SHA256 sidecar, and GUI-only contents without contacting any WLC.
"""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path


REQUIRED_FILES = {
    "WlcRoleAclCollectorGUI.exe",
    "USER_GUIDE_KO.md",
    "USER_GUIDE_KO.html",
    "DEVELOPER_GUIDE_KO.md",
    "DEVELOPER_GUIDE_KO.html",
    "ERROR_CODES_KO.md",
    "ERROR_CODES_KO.html",
    "DIAGNOSTIC_MODE_KO.md",
    "DIAGNOSTIC_MODE_KO.html",
    "SECURITY_MODEL_KO.md",
    "SECURITY_MODEL_KO.html",
    "DEPENDENCY_AUDIT_EXCEPTIONS_KO.md",
    "DEPENDENCY_AUDIT_EXCEPTIONS_KO.html",
    "config/role_networks.example.xlsx",
}

REQUIRED_MOCK_SCENARIOS = {
    "config/mock_scenarios/auth_failed.json",
    "config/mock_scenarios/missing_config.json",
    "config/mock_scenarios/permission_denied.json",
    "config/mock_scenarios/success_minimal.json",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a WLC Role ACL Collector Windows release ZIP.")
    parser.add_argument("--zip", dest="zip_path", type=Path, help="release ZIP path")
    parser.add_argument("--dist", type=Path, default=Path("dist"), help="directory containing a release ZIP")
    parser.add_argument("--sha256", type=Path, help="SHA256 sidecar file to verify")
    args = parser.parse_args(argv)

    zip_path = args.zip_path or _find_latest_zip(args.dist)
    if not zip_path.exists():
        raise SystemExit(f"Release ZIP does not exist: {zip_path}")
    if zip_path.stat().st_size <= 0:
        raise SystemExit(f"Release ZIP is empty: {zip_path}")

    names = _read_zip_names(zip_path)
    _verify_required_files(names)

    if args.sha256:
        _verify_sha256(zip_path, args.sha256)

    print(f"Verified release package: {zip_path}")
    return 0


def _find_latest_zip(dist_dir: Path) -> Path:
    candidates = sorted(
        dist_dir.glob("WlcRoleAclCollectorGUI*.zip"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise SystemExit(f"No GUI release ZIP was found in {dist_dir}")
    return candidates[0]


def _read_zip_names(zip_path: Path) -> set[str]:
    try:
        with zipfile.ZipFile(zip_path) as archive:
            bad_file = archive.testzip()
            if bad_file:
                raise SystemExit(f"Release ZIP contains a corrupt entry: {bad_file}")
            return {name.replace("\\", "/").rstrip("/") for name in archive.namelist()}
    except zipfile.BadZipFile as exc:
        raise SystemExit(f"Release ZIP is not a valid ZIP file: {zip_path}") from exc


def _verify_required_files(names: set[str]) -> None:
    missing = sorted((REQUIRED_FILES | REQUIRED_MOCK_SCENARIOS) - names)
    if missing:
        raise SystemExit("Release ZIP is missing required files:\n" + "\n".join(f"- {item}" for item in missing))
    if "WlcRoleAclCollectorCLI.exe" in names:
        raise SystemExit("Removed CLI executable must not be included in the GUI ZIP.")


def _verify_sha256(zip_path: Path, checksum_path: Path) -> None:
    if not checksum_path.exists():
        raise SystemExit(f"SHA256 file does not exist: {checksum_path}")

    parts = checksum_path.read_text(encoding="ascii").strip().split()
    if len(parts) < 2:
        raise SystemExit(f"SHA256 file must contain '<hash>  <filename>': {checksum_path}")

    expected_hash = parts[0].lower()
    expected_name = parts[-1]
    if len(expected_hash) != 64 or any(char not in "0123456789abcdef" for char in expected_hash):
        raise SystemExit(f"SHA256 hash is invalid: {expected_hash}")
    if expected_name != zip_path.name:
        raise SystemExit(f"SHA256 filename mismatch: expected {zip_path.name}, got {expected_name}")

    actual_hash = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    if actual_hash != expected_hash:
        raise SystemExit(f"SHA256 mismatch for {zip_path.name}: expected {expected_hash}, got {actual_hash}")


if __name__ == "__main__":
    raise SystemExit(main())

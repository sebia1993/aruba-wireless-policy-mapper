"""Small atomic file-writing helpers used by reports and diagnostic artifacts."""

from __future__ import annotations

import os
import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator


@contextmanager
def atomic_output_path(path: Path) -> Iterator[Path]:
    """Yield a same-directory temporary path and replace the destination on success."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.stem}.{uuid.uuid4().hex}.tmp{path.suffix}")
    try:
        yield temporary
        with temporary.open("rb+") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_text(path: Path, value: str, *, encoding: str = "utf-8") -> None:
    with atomic_output_path(path) as temporary:
        with temporary.open("w", encoding=encoding, newline="") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())


def commit_staged_files(
    artifacts: Iterable[tuple[Path, Path]],
    *,
    transaction_id: str | None = None,
) -> None:
    """Commit multiple completed files and roll back earlier replacements on failure."""

    artifact_pairs = tuple((Path(staging), Path(destination)) for staging, destination in artifacts)
    if not artifact_pairs:
        return
    for staging, destination in artifact_pairs:
        if not staging.exists():
            raise FileNotFoundError(f"Staging file does not exist: {staging}")
        if staging.parent != destination.parent:
            raise ValueError("Staging and destination files must use the same parent directory.")
        with staging.open("rb+") as handle:
            os.fsync(handle.fileno())

    token = transaction_id or uuid.uuid4().hex
    backups: dict[Path, Path] = {}
    committed: list[Path] = []
    preserved_backups: set[Path] = set()
    try:
        for _staging, destination in artifact_pairs:
            if destination.exists():
                backup = destination.with_name(
                    f".{destination.stem}.{token}.backup{destination.suffix}"
                )
                shutil.copy2(destination, backup)
                backups[destination] = backup

        for staging, destination in artifact_pairs:
            staging.replace(destination)
            committed.append(destination)
    except Exception as exc:
        restore_errors: list[str] = []
        for destination in reversed(committed):
            backup = backups.get(destination)
            try:
                if backup is not None and backup.exists():
                    backup.replace(destination)
                else:
                    destination.unlink(missing_ok=True)
            except OSError as restore_exc:
                restore_errors.append(f"{destination.name}: {restore_exc}")
                if backup is not None and backup.exists():
                    preserved_backups.add(backup)
        if restore_errors:
            exc.add_note("Unable to restore previous files: " + "; ".join(restore_errors))
        raise
    finally:
        for staging, _destination in artifact_pairs:
            staging.unlink(missing_ok=True)
        for backup in backups.values():
            if backup not in preserved_backups:
                backup.unlink(missing_ok=True)

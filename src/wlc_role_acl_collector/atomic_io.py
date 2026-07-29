"""Small atomic file-writing helpers used by reports and diagnostic artifacts."""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


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

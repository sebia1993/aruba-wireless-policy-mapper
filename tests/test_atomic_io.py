from pathlib import Path

import pytest

from wlc_role_acl_collector.atomic_io import atomic_output_path, atomic_write_text


def test_atomic_write_text_replaces_destination(tmp_path):
    destination = tmp_path / "result.txt"
    destination.write_text("old", encoding="utf-8")

    atomic_write_text(destination, "new")

    assert destination.read_text(encoding="utf-8") == "new"
    assert not list(tmp_path.glob(".*.tmp*"))


def test_atomic_output_path_keeps_existing_file_when_writer_fails(tmp_path):
    destination = tmp_path / "result.xlsx"
    destination.write_bytes(b"old")

    with pytest.raises(RuntimeError):
        with atomic_output_path(destination) as temporary:
            Path(temporary).write_bytes(b"partial")
            raise RuntimeError("write failed")

    assert destination.read_bytes() == b"old"
    assert not list(tmp_path.glob(".*.tmp*"))

from pathlib import Path

import pytest

from wlc_role_acl_collector.atomic_io import (
    atomic_output_path,
    atomic_write_text,
    commit_staged_files,
)


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


def test_commit_staged_files_rolls_back_first_replacement_when_second_fails(monkeypatch, tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    staged_first = tmp_path / ".first.staging.txt"
    staged_second = tmp_path / ".second.staging.txt"
    first.write_text("old-first", encoding="utf-8")
    second.write_text("old-second", encoding="utf-8")
    staged_first.write_text("new-first", encoding="utf-8")
    staged_second.write_text("new-second", encoding="utf-8")
    original_replace = Path.replace

    def replace_with_second_failure(path, target):
        if path == staged_second:
            raise OSError("second replacement failed")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", replace_with_second_failure)

    with pytest.raises(OSError, match="second replacement failed"):
        commit_staged_files(
            ((staged_first, first), (staged_second, second)),
            transaction_id="test",
        )

    assert first.read_text(encoding="utf-8") == "old-first"
    assert second.read_text(encoding="utf-8") == "old-second"
    assert not staged_first.exists()
    assert not staged_second.exists()
    assert not list(tmp_path.glob(".*.backup.*"))

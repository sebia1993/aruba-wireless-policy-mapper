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


def test_atomic_cleanup_failure_preserves_original_write_error(monkeypatch, tmp_path):
    real_unlink = Path.unlink

    def deny_temporary_cleanup(path, *args, **kwargs):
        if ".tmp" in path.name:
            raise PermissionError("synthetic cleanup lock")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_temporary_cleanup)
    with pytest.raises(RuntimeError, match="original write failed") as caught:
        with atomic_output_path(tmp_path / "result.txt") as temporary:
            temporary.write_text("partial", encoding="utf-8")
            raise RuntimeError("original write failed")

    assert any("cleanup" in note for note in caught.value.__notes__)
    assert not (tmp_path / "result.txt").exists()


def test_backup_cleanup_lock_does_not_report_successful_commit_as_failed(monkeypatch, tmp_path, caplog):
    destination = tmp_path / "result.txt"
    staging = tmp_path / ".result.staging.txt"
    destination.write_text("old", encoding="utf-8")
    staging.write_text("new", encoding="utf-8")
    real_unlink = Path.unlink

    def deny_backup_cleanup(path, *args, **kwargs):
        if ".backup" in path.name:
            raise PermissionError("synthetic backup lock")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_backup_cleanup)
    commit_staged_files(((staging, destination),), transaction_id="synthetic")

    assert destination.read_text(encoding="utf-8") == "new"
    assert list(tmp_path.glob(".*.backup.*"))[0].read_text(encoding="utf-8") == "old"
    assert "cleanup" in caplog.text.lower()


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

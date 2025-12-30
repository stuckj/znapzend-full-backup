"""Tests for znapzend_full.backup.hash_tracker module."""

import pytest
from pathlib import Path

from znapzend_full.backup.hash_tracker import HashTracker


class TestHashTracker:
    """Tests for HashTracker class."""

    def test_init(self, temp_dir):
        tracker = HashTracker(temp_dir)
        assert tracker.base_path == temp_dir

    def test_get_hash_path(self, temp_dir):
        tracker = HashTracker(temp_dir)
        file_path = temp_dir / "efi" / "nvme0n1p1.img"
        hash_path = tracker._get_hash_path(file_path)
        assert hash_path == temp_dir / "efi" / "nvme0n1p1.img.sha256"

    def test_read_stored_hash_nonexistent(self, temp_dir):
        tracker = HashTracker(temp_dir)
        hash_path = temp_dir / "nonexistent.sha256"
        assert tracker._read_stored_hash(hash_path) is None

    def test_read_stored_hash_with_filename(self, temp_dir):
        tracker = HashTracker(temp_dir)
        hash_path = temp_dir / "test.sha256"
        hash_path.write_text("abc123def456  test.txt\n")
        assert tracker._read_stored_hash(hash_path) == "abc123def456"

    def test_read_stored_hash_without_filename(self, temp_dir):
        tracker = HashTracker(temp_dir)
        hash_path = temp_dir / "test.sha256"
        hash_path.write_text("abc123def456\n")
        assert tracker._read_stored_hash(hash_path) == "abc123def456"

    def test_read_stored_hash_empty(self, temp_dir):
        tracker = HashTracker(temp_dir)
        hash_path = temp_dir / "test.sha256"
        hash_path.write_text("")
        assert tracker._read_stored_hash(hash_path) is None


class TestUpdateTextFile:
    """Tests for update_text_file method."""

    def test_create_new_file(self, temp_dir):
        tracker = HashTracker(temp_dir)
        content = "Hello, World!"

        result = tracker.update_text_file("test/file.txt", content)

        assert result is True
        assert (temp_dir / "test" / "file.txt").exists()
        assert (temp_dir / "test" / "file.txt").read_text() == content
        assert (temp_dir / "test" / "file.txt.sha256").exists()

    def test_update_unchanged_file(self, temp_dir):
        tracker = HashTracker(temp_dir)
        content = "Hello, World!"

        # First write
        tracker.update_text_file("test/file.txt", content)

        # Second write with same content
        result = tracker.update_text_file("test/file.txt", content)

        assert result is False  # No change

    def test_update_changed_file(self, temp_dir):
        tracker = HashTracker(temp_dir)

        # First write
        tracker.update_text_file("test/file.txt", "Original content")

        # Second write with different content
        result = tracker.update_text_file("test/file.txt", "Updated content")

        assert result is True
        assert (temp_dir / "test" / "file.txt").read_text() == "Updated content"

    def test_creates_subdirectories(self, temp_dir):
        tracker = HashTracker(temp_dir)

        tracker.update_text_file("deep/nested/path/file.txt", "content")

        assert (temp_dir / "deep" / "nested" / "path" / "file.txt").exists()


class TestUpdateFile:
    """Tests for update_file method."""

    def test_create_new_binary_file(self, temp_dir):
        tracker = HashTracker(temp_dir)

        def write_content(path: Path):
            path.write_bytes(b"binary content")

        result = tracker.update_file("efi/partition.img", write_content)

        assert result is True
        assert (temp_dir / "efi" / "partition.img").exists()
        assert (temp_dir / "efi" / "partition.img").read_bytes() == b"binary content"
        assert (temp_dir / "efi" / "partition.img.sha256").exists()

    def test_update_unchanged_binary_file(self, temp_dir):
        tracker = HashTracker(temp_dir)

        def write_content(path: Path):
            path.write_bytes(b"binary content")

        # First write
        tracker.update_file("efi/partition.img", write_content)

        # Second write with same content
        result = tracker.update_file("efi/partition.img", write_content)

        assert result is False

    def test_update_changed_binary_file(self, temp_dir):
        tracker = HashTracker(temp_dir)

        def write_original(path: Path):
            path.write_bytes(b"original")

        def write_updated(path: Path):
            path.write_bytes(b"updated")

        # First write
        tracker.update_file("efi/partition.img", write_original)

        # Second write with different content
        result = tracker.update_file("efi/partition.img", write_updated)

        assert result is True
        assert (temp_dir / "efi" / "partition.img").read_bytes() == b"updated"

    def test_cleanup_on_error(self, temp_dir):
        tracker = HashTracker(temp_dir)

        def failing_writer(path: Path):
            path.write_bytes(b"partial")
            raise RuntimeError("Simulated failure")

        with pytest.raises(RuntimeError):
            tracker.update_file("test/fail.bin", failing_writer)

        # Temp file should be cleaned up
        assert not any(f.name.startswith(".fail.bin.") for f in temp_dir.rglob("*"))


class TestHasChanged:
    """Tests for has_changed method."""

    def test_nonexistent_file(self, temp_dir):
        tracker = HashTracker(temp_dir)
        assert tracker.has_changed("nonexistent.txt") is True

    def test_file_without_hash(self, temp_dir):
        tracker = HashTracker(temp_dir)
        (temp_dir / "orphan.txt").write_text("content")

        assert tracker.has_changed("orphan.txt") is True

    def test_unchanged_file(self, temp_dir):
        tracker = HashTracker(temp_dir)
        tracker.update_text_file("test.txt", "content")

        assert tracker.has_changed("test.txt") is False

    def test_manually_modified_file(self, temp_dir):
        tracker = HashTracker(temp_dir)
        tracker.update_text_file("test.txt", "original")

        # Manually modify file without updating hash
        (temp_dir / "test.txt").write_text("modified")

        assert tracker.has_changed("test.txt") is True


class TestGetAllTrackedFiles:
    """Tests for get_all_tracked_files method."""

    def test_empty_directory(self, temp_dir):
        tracker = HashTracker(temp_dir)
        assert tracker.get_all_tracked_files() == []

    def test_excludes_hash_files(self, temp_dir):
        tracker = HashTracker(temp_dir)
        tracker.update_text_file("file1.txt", "content1")
        tracker.update_text_file("file2.txt", "content2")

        files = tracker.get_all_tracked_files()

        assert len(files) == 2
        assert Path("file1.txt") in files
        assert Path("file2.txt") in files
        # No .sha256 files
        assert not any(f.suffix == ".sha256" for f in files)

    def test_nested_files(self, temp_dir):
        tracker = HashTracker(temp_dir)
        tracker.update_text_file("efi/part1.img", "efi1")
        tracker.update_text_file("gpt/disk1.sgdisk", "gpt1")
        tracker.update_text_file("zfs/pool.properties", "props")

        files = tracker.get_all_tracked_files()

        assert len(files) == 3


class TestCleanupOrphanedHashes:
    """Tests for cleanup_orphaned_hashes method."""

    def test_no_orphans(self, temp_dir):
        tracker = HashTracker(temp_dir)
        tracker.update_text_file("test.txt", "content")

        removed = tracker.cleanup_orphaned_hashes()

        assert removed == []
        assert (temp_dir / "test.txt.sha256").exists()

    def test_removes_orphaned_hash(self, temp_dir):
        tracker = HashTracker(temp_dir)
        tracker.update_text_file("test.txt", "content")

        # Delete the data file but keep the hash
        (temp_dir / "test.txt").unlink()

        removed = tracker.cleanup_orphaned_hashes()

        assert len(removed) == 1
        assert not (temp_dir / "test.txt.sha256").exists()

    def test_mixed_orphaned_and_valid(self, temp_dir):
        tracker = HashTracker(temp_dir)
        tracker.update_text_file("valid.txt", "content")
        tracker.update_text_file("orphan.txt", "content")

        # Delete one data file
        (temp_dir / "orphan.txt").unlink()

        removed = tracker.cleanup_orphaned_hashes()

        assert len(removed) == 1
        assert (temp_dir / "valid.txt.sha256").exists()
        assert not (temp_dir / "orphan.txt.sha256").exists()

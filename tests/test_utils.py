"""Tests for znapzend_full.utils module."""

import pytest
from pathlib import Path
import hashlib

from znapzend_full.utils import (
    parse_size,
    format_size,
    compute_sha256,
    compute_sha256_string,
    hash_matches,
    save_hash,
)


class TestParseSize:
    """Tests for parse_size function."""

    def test_bytes(self):
        assert parse_size("100B") == 100
        assert parse_size("100b") == 100

    def test_kilobytes(self):
        assert parse_size("1K") == 1024
        assert parse_size("2K") == 2048
        assert parse_size("1.5K") == 1536

    def test_megabytes(self):
        assert parse_size("1M") == 1024 * 1024
        assert parse_size("10M") == 10 * 1024 * 1024

    def test_gigabytes(self):
        assert parse_size("1G") == 1024 ** 3
        assert parse_size("2.5G") == int(2.5 * 1024 ** 3)

    def test_terabytes(self):
        assert parse_size("1T") == 1024 ** 4

    def test_petabytes(self):
        assert parse_size("1P") == 1024 ** 5

    def test_no_suffix(self):
        assert parse_size("12345") == 12345

    def test_empty_string(self):
        assert parse_size("") == 0

    def test_dash(self):
        assert parse_size("-") == 0

    def test_invalid(self):
        assert parse_size("invalid") == 0

    def test_case_insensitive(self):
        assert parse_size("1g") == parse_size("1G")
        assert parse_size("1m") == parse_size("1M")


class TestFormatSize:
    """Tests for format_size function."""

    def test_bytes(self):
        assert format_size(500) == "500.0B"

    def test_kilobytes(self):
        assert format_size(1024) == "1.0K"
        assert format_size(2048) == "2.0K"

    def test_megabytes(self):
        assert format_size(1024 * 1024) == "1.0M"

    def test_gigabytes(self):
        assert format_size(1024 ** 3) == "1.0G"
        assert format_size(int(2.5 * 1024 ** 3)) == "2.5G"

    def test_terabytes(self):
        assert format_size(1024 ** 4) == "1.0T"

    def test_zero(self):
        assert format_size(0) == "0.0B"


class TestComputeSha256:
    """Tests for compute_sha256 function."""

    def test_compute_hash(self, temp_dir):
        test_file = temp_dir / "test.txt"
        content = b"Hello, World!"
        test_file.write_bytes(content)

        result = compute_sha256(test_file)

        expected = hashlib.sha256(content).hexdigest()
        assert result == expected

    def test_empty_file(self, temp_dir):
        test_file = temp_dir / "empty.txt"
        test_file.write_bytes(b"")

        result = compute_sha256(test_file)

        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected

    def test_large_file(self, temp_dir):
        """Test hash computation on a file larger than buffer size."""
        test_file = temp_dir / "large.bin"
        # Create a 1MB file
        content = b"x" * (1024 * 1024)
        test_file.write_bytes(content)

        result = compute_sha256(test_file)

        expected = hashlib.sha256(content).hexdigest()
        assert result == expected

    def test_binary_content(self, temp_dir):
        test_file = temp_dir / "binary.bin"
        content = bytes(range(256))
        test_file.write_bytes(content)

        result = compute_sha256(test_file)

        expected = hashlib.sha256(content).hexdigest()
        assert result == expected


class TestComputeSha256String:
    """Tests for compute_sha256_string function."""

    def test_simple_string(self):
        result = compute_sha256_string("Hello, World!")
        expected = hashlib.sha256(b"Hello, World!").hexdigest()
        assert result == expected

    def test_empty_string(self):
        result = compute_sha256_string("")
        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected

    def test_unicode(self):
        result = compute_sha256_string("Hello, 世界! 🌍")
        expected = hashlib.sha256("Hello, 世界! 🌍".encode()).hexdigest()
        assert result == expected


class TestHashMatches:
    """Tests for hash_matches function."""

    def test_matching_hash(self, temp_dir):
        test_file = temp_dir / "test.txt"
        hash_file = temp_dir / "test.txt.sha256"

        content = b"Test content"
        test_file.write_bytes(content)

        # Write correct hash
        expected_hash = hashlib.sha256(content).hexdigest()
        hash_file.write_text(f"{expected_hash}  test.txt\n")

        assert hash_matches(test_file, hash_file) is True

    def test_non_matching_hash(self, temp_dir):
        test_file = temp_dir / "test.txt"
        hash_file = temp_dir / "test.txt.sha256"

        test_file.write_bytes(b"Test content")
        hash_file.write_text("0" * 64 + "  test.txt\n")  # Wrong hash

        assert hash_matches(test_file, hash_file) is False

    def test_missing_file(self, temp_dir):
        test_file = temp_dir / "nonexistent.txt"
        hash_file = temp_dir / "nonexistent.txt.sha256"

        assert hash_matches(test_file, hash_file) is False

    def test_missing_hash_file(self, temp_dir):
        test_file = temp_dir / "test.txt"
        hash_file = temp_dir / "test.txt.sha256"

        test_file.write_bytes(b"Test content")
        # hash_file doesn't exist

        assert hash_matches(test_file, hash_file) is False

    def test_hash_only_format(self, temp_dir):
        """Test with hash file containing only the hash (no filename)."""
        test_file = temp_dir / "test.txt"
        hash_file = temp_dir / "test.txt.sha256"

        content = b"Test content"
        test_file.write_bytes(content)

        # Write hash only (no filename)
        expected_hash = hashlib.sha256(content).hexdigest()
        hash_file.write_text(expected_hash)

        assert hash_matches(test_file, hash_file) is True


class TestSaveHash:
    """Tests for save_hash function."""

    def test_save_hash(self, temp_dir):
        test_file = temp_dir / "test.txt"
        hash_file = temp_dir / "test.txt.sha256"

        content = b"Test content"
        test_file.write_bytes(content)

        save_hash(test_file, hash_file)

        assert hash_file.exists()

        # Verify format
        hash_content = hash_file.read_text()
        expected_hash = hashlib.sha256(content).hexdigest()
        assert hash_content.startswith(expected_hash)
        assert "test.txt" in hash_content

    def test_saved_hash_matches(self, temp_dir):
        """Test that saved hash can be verified."""
        test_file = temp_dir / "test.txt"
        hash_file = temp_dir / "test.txt.sha256"

        test_file.write_bytes(b"Test content")
        save_hash(test_file, hash_file)

        assert hash_matches(test_file, hash_file) is True

    def test_overwrite_existing(self, temp_dir):
        test_file = temp_dir / "test.txt"
        hash_file = temp_dir / "test.txt.sha256"

        # Initial content
        test_file.write_bytes(b"Initial content")
        save_hash(test_file, hash_file)
        initial_hash = hash_file.read_text()

        # Updated content
        test_file.write_bytes(b"Updated content")
        save_hash(test_file, hash_file)
        updated_hash = hash_file.read_text()

        assert initial_hash != updated_hash

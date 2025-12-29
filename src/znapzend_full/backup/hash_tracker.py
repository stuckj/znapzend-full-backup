"""
Hash-based change tracking for efficient backups.

This module manages hash tracking for backup files, ensuring that
unchanged files don't cause unnecessary ZFS snapshot space usage.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Callable

from ..utils import compute_sha256, compute_sha256_string

logger = logging.getLogger(__name__)


class HashTracker:
    """Tracks file hashes to detect changes and minimize ZFS snapshot size.

    The tracker stores files alongside their SHA256 hashes. When updating
    a file, it first writes to a temp location, computes the hash, and
    only replaces the target if the hash differs.
    """

    def __init__(self, base_path: Path):
        """Initialize hash tracker.

        Args:
            base_path: Base directory for storing backups (typically the
                       mountpoint of the metadata dataset).
        """
        self.base_path = Path(base_path)

    def _get_hash_path(self, file_path: Path) -> Path:
        """Get the hash file path for a given file.

        Args:
            file_path: Path to the file.

        Returns:
            Path to the corresponding hash file.
        """
        return file_path.with_suffix(file_path.suffix + ".sha256")

    def _read_stored_hash(self, hash_path: Path) -> str | None:
        """Read the stored hash from a hash file.

        Args:
            hash_path: Path to hash file.

        Returns:
            Hash string or None if file doesn't exist.
        """
        if not hash_path.exists():
            return None
        try:
            content = hash_path.read_text().strip()
            # Handle both "hash" and "hash  filename" formats
            return content.split()[0] if content else None
        except (OSError, IndexError):
            return None

    def update_file(
        self,
        relative_path: str,
        content_generator: Callable[[Path], None],
    ) -> bool:
        """Update a file if its content has changed.

        Args:
            relative_path: Path relative to base_path.
            content_generator: Function that writes content to a given path.

        Returns:
            True if file was updated (content changed), False otherwise.
        """
        target_path = self.base_path / relative_path
        hash_path = self._get_hash_path(target_path)

        # Ensure target directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file first
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=target_path.parent,
            prefix=f".{target_path.name}.",
        ) as tmp:
            tmp_path = Path(tmp.name)

        try:
            # Generate content to temp file
            content_generator(tmp_path)

            # Compute hash of new content
            new_hash = compute_sha256(tmp_path)

            # Get stored hash
            stored_hash = self._read_stored_hash(hash_path)

            if new_hash == stored_hash:
                # No change, clean up temp file
                tmp_path.unlink()
                logger.debug(f"No change detected for {relative_path}")
                return False

            # Content changed, replace the file
            shutil.move(str(tmp_path), str(target_path))
            hash_path.write_text(f"{new_hash}  {target_path.name}\n")
            logger.info(f"Updated {relative_path} (hash changed)")
            return True

        except Exception:
            # Clean up temp file on error
            if tmp_path.exists():
                tmp_path.unlink()
            raise

    def update_text_file(
        self,
        relative_path: str,
        content: str,
    ) -> bool:
        """Update a text file if its content has changed.

        Args:
            relative_path: Path relative to base_path.
            content: Text content to write.

        Returns:
            True if file was updated, False otherwise.
        """
        target_path = self.base_path / relative_path
        hash_path = self._get_hash_path(target_path)

        # Ensure target directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Compute hash of new content
        new_hash = compute_sha256_string(content)

        # Get stored hash
        stored_hash = self._read_stored_hash(hash_path)

        if new_hash == stored_hash:
            logger.debug(f"No change detected for {relative_path}")
            return False

        # Content changed, update file
        target_path.write_text(content)
        hash_path.write_text(f"{new_hash}  {target_path.name}\n")
        logger.info(f"Updated {relative_path} (hash changed)")
        return True

    def has_changed(self, relative_path: str) -> bool:
        """Check if a file's content has changed since last backup.

        Args:
            relative_path: Path relative to base_path.

        Returns:
            True if content differs from stored hash or file doesn't exist.
        """
        target_path = self.base_path / relative_path
        hash_path = self._get_hash_path(target_path)

        if not target_path.exists():
            return True

        stored_hash = self._read_stored_hash(hash_path)
        if stored_hash is None:
            return True

        current_hash = compute_sha256(target_path)
        return current_hash != stored_hash

    def get_all_tracked_files(self) -> list[Path]:
        """Get all tracked files in the base path.

        Returns:
            List of file paths (excluding hash files).
        """
        files = []
        for path in self.base_path.rglob("*"):
            if path.is_file() and not path.suffix == ".sha256":
                files.append(path.relative_to(self.base_path))
        return files

    def cleanup_orphaned_hashes(self) -> list[Path]:
        """Remove hash files that don't have corresponding data files.

        Returns:
            List of removed hash file paths.
        """
        removed = []
        for hash_path in self.base_path.rglob("*.sha256"):
            # The data file path (remove .sha256 suffix)
            data_path = hash_path.with_suffix("")
            if not data_path.exists():
                hash_path.unlink()
                removed.append(hash_path)
                logger.info(f"Removed orphaned hash file: {hash_path}")
        return removed

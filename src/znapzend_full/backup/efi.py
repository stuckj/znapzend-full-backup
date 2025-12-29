"""
EFI partition backup functionality.

This module handles backing up EFI partitions using dd.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..utils import run_command
from .hash_tracker import HashTracker

logger = logging.getLogger(__name__)


def backup_single_efi(
    partition: str,
    tracker: HashTracker,
) -> bool:
    """Backup a single EFI partition.

    Args:
        partition: Device path (e.g., '/dev/nvme0n1p1').
        tracker: HashTracker for change detection.

    Returns:
        True if backup was updated, False if unchanged.
    """
    # Create filename from partition path
    # /dev/nvme0n1p1 -> nvme0n1p1
    partition_name = Path(partition).name
    relative_path = f"efi/{partition_name}.img"

    logger.info(f"Backing up EFI partition {partition}")

    def write_efi(output_path: Path) -> None:
        """Write EFI partition to file using dd."""
        run_command([
            "dd",
            f"if={partition}",
            f"of={output_path}",
            "bs=4M",
            "status=none",
        ])

    return tracker.update_file(relative_path, write_efi)


def backup_efi_partitions(
    partitions: list[str],
    tracker: HashTracker,
) -> dict[str, bool]:
    """Backup multiple EFI partitions.

    Args:
        partitions: List of device paths.
        tracker: HashTracker for change detection.

    Returns:
        Dict mapping partition to whether it was updated.
    """
    results = {}
    for partition in partitions:
        try:
            results[partition] = backup_single_efi(partition, tracker)
        except Exception as e:
            logger.error(f"Failed to backup EFI partition {partition}: {e}")
            results[partition] = False
    return results


def restore_efi(
    backup_path: Path,
    target_partition: str,
    dry_run: bool = False,
) -> None:
    """Restore an EFI partition from backup.

    Args:
        backup_path: Path to the EFI image file.
        target_partition: Target device path.
        dry_run: If True, only log what would be done.

    Raises:
        FileNotFoundError: If backup file doesn't exist.
        subprocess.CalledProcessError: If restore fails.
    """
    if not backup_path.exists():
        raise FileNotFoundError(f"EFI backup not found: {backup_path}")

    logger.info(f"Restoring EFI partition to {target_partition}")

    if dry_run:
        logger.info(f"[DRY RUN] Would restore {backup_path} to {target_partition}")
        return

    run_command([
        "dd",
        f"if={backup_path}",
        f"of={target_partition}",
        "bs=4M",
        "status=progress",
    ])
    logger.info(f"Successfully restored EFI partition to {target_partition}")

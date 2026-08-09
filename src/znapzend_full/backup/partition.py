"""
GPT partition layout backup functionality.

This module handles backing up GPT partition tables using sgdisk.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..utils import run_command
from .hash_tracker import HashTracker

logger = logging.getLogger(__name__)


def backup_single_gpt(
    disk: str,
    tracker: HashTracker,
) -> dict[str, bool]:
    """Backup GPT partition table for a single disk.

    Creates both binary (for restore) and human-readable (for reference) backups.

    Args:
        disk: Device path (e.g., '/dev/nvme0n1').
        tracker: HashTracker for change detection.

    Returns:
        Dict with 'binary' and 'readable' keys indicating if each was updated.
    """
    disk_name = Path(disk).name
    results = {}

    # Binary backup (for restoration)
    binary_path = f"gpt/{disk_name}.sgdisk"
    logger.info(f"Backing up GPT (binary) for {disk}")

    def write_binary(output_path: Path) -> None:
        run_command(["sgdisk", "--backup", str(output_path), disk])

    try:
        results["binary"] = tracker.update_file(binary_path, write_binary)
    except Exception as e:
        logger.error(f"Failed to backup GPT (binary) for {disk}: {e}")
        results["binary"] = False

    # Human-readable backup (for reference)
    readable_path = f"gpt/{disk_name}.txt"
    logger.info(f"Backing up GPT (readable) for {disk}")

    try:
        result = run_command(["sgdisk", "--print", disk])
        results["readable"] = tracker.update_text_file(readable_path, result.stdout)
    except Exception as e:
        logger.error(f"Failed to backup GPT (readable) for {disk}: {e}")
        results["readable"] = False

    return results


def backup_gpt_layouts(
    disks: list[str],
    tracker: HashTracker,
) -> dict[str, dict[str, bool]]:
    """Backup GPT partition tables for multiple disks.

    Args:
        disks: List of disk device paths.
        tracker: HashTracker for change detection.

    Returns:
        Dict mapping disk to results dict with 'binary' and 'readable' status.
    """
    results = {}
    for disk in disks:
        results[disk] = backup_single_gpt(disk, tracker)
    return results


def restore_gpt(
    backup_path: Path,
    target_disk: str,
    dry_run: bool = False,
) -> None:
    """Restore GPT partition table from backup.

    Args:
        backup_path: Path to the sgdisk backup file.
        target_disk: Target disk device path.
        dry_run: If True, only log what would be done.

    Raises:
        FileNotFoundError: If backup file doesn't exist.
        subprocess.CalledProcessError: If restore fails.
    """
    if not backup_path.exists():
        raise FileNotFoundError(f"GPT backup not found: {backup_path}")

    logger.info(f"Restoring GPT partition table to {target_disk}")

    if dry_run:
        logger.info(f"[DRY RUN] Would restore {backup_path} to {target_disk}")
        return

    # First, zap any existing partition data
    run_command(["sgdisk", "--zap-all", target_disk])

    # Restore from backup
    run_command(["sgdisk", "--load-backup", str(backup_path), target_disk])

    # Randomize GUIDs to avoid conflicts with source disk
    run_command(["sgdisk", "--randomize-guids", target_disk])

    logger.info(f"Successfully restored GPT partition table to {target_disk}")


def get_partition_info(disk: str) -> str:
    """Get human-readable partition information for a disk.

    Args:
        disk: Device path.

    Returns:
        Partition table information as string.
    """
    result = run_command(["sgdisk", "--print", disk])
    return result.stdout


def verify_gpt(disk: str) -> tuple[bool, str]:
    """Verify GPT partition table integrity.

    Args:
        disk: Device path.

    Returns:
        Tuple of (is_valid, message).
    """
    result = run_command(["sgdisk", "--verify", disk], check=False)
    is_valid = result.returncode == 0
    message = result.stdout + result.stderr
    return is_valid, message

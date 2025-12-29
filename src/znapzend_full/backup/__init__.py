"""
Backup functionality for znapzend-full.

This module handles backing up non-ZFS system data including:
- EFI partitions
- GPT partition layouts
- ZFS/zpool properties
"""

from .efi import backup_efi_partitions
from .partition import backup_gpt_layouts
from .zfs_props import backup_zfs_properties, backup_zpool_properties, backup_zpool_status
from .hash_tracker import HashTracker

__all__ = [
    "backup_efi_partitions",
    "backup_gpt_layouts",
    "backup_zfs_properties",
    "backup_zpool_properties",
    "backup_zpool_status",
    "HashTracker",
]

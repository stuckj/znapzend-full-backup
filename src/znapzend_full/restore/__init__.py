"""
Restore functionality for znapzend-full.

Provides interactive restore capabilities for full system recovery.
"""

from .interactive import main as interactive_main
from .ssh_client import SSHClient
from .zfs_restore import restore_dataset, restore_pool
from .partition_restore import restore_gpt, restore_efi

__all__ = [
    "interactive_main",
    "SSHClient",
    "restore_dataset",
    "restore_pool",
    "restore_gpt",
    "restore_efi",
]

"""
ZFS and zpool properties backup functionality.

This module handles backing up:
- zpool status (vdev layout)
- zpool properties
- ZFS dataset properties (all datasets recursively)
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..utils import run_command
from .hash_tracker import HashTracker

logger = logging.getLogger(__name__)


def backup_zpool_status(
    pool: str,
    tracker: HashTracker,
) -> bool:
    """Backup zpool status (vdev layout).

    Args:
        pool: Pool name.
        tracker: HashTracker for change detection.

    Returns:
        True if backup was updated, False if unchanged.
    """
    relative_path = f"zpool/{pool}.status"
    logger.info(f"Backing up zpool status for {pool}")

    try:
        result = run_command(["zpool", "status", pool])
        return tracker.update_text_file(relative_path, result.stdout)
    except Exception as e:
        logger.error(f"Failed to backup zpool status for {pool}: {e}")
        return False


def backup_zpool_properties(
    pool: str,
    tracker: HashTracker,
) -> bool:
    """Backup zpool properties.

    Args:
        pool: Pool name.
        tracker: HashTracker for change detection.

    Returns:
        True if backup was updated, False if unchanged.
    """
    relative_path = f"zpool/{pool}.properties"
    logger.info(f"Backing up zpool properties for {pool}")

    try:
        result = run_command(["zpool", "get", "all", pool])
        return tracker.update_text_file(relative_path, result.stdout)
    except Exception as e:
        logger.error(f"Failed to backup zpool properties for {pool}: {e}")
        return False


def backup_zfs_properties(
    dataset: str,
    tracker: HashTracker,
    recursive: bool = True,
) -> bool:
    """Backup ZFS dataset properties.

    Backs up properties for all datasets under the specified dataset/pool.

    Args:
        dataset: Dataset or pool name.
        tracker: HashTracker for change detection.
        recursive: Whether to include child datasets.

    Returns:
        True if backup was updated, False if unchanged.
    """
    # Use pool name for filename (first component)
    pool_name = dataset.split("/")[0]
    relative_path = f"zfs/{pool_name}.properties"
    logger.info(f"Backing up ZFS properties for {dataset} (recursive={recursive})")

    try:
        cmd = ["zfs", "get", "all"]
        if recursive:
            cmd.append("-r")
        cmd.append(dataset)
        result = run_command(cmd)
        return tracker.update_text_file(relative_path, result.stdout)
    except Exception as e:
        logger.error(f"Failed to backup ZFS properties for {dataset}: {e}")
        return False


def backup_all_zpool_info(
    pools: list[str],
    tracker: HashTracker,
) -> dict[str, dict[str, bool]]:
    """Backup all zpool information (status and properties).

    Args:
        pools: List of pool names.
        tracker: HashTracker for change detection.

    Returns:
        Dict mapping pool name to results dict with 'status' and 'properties' status.
    """
    results = {}
    for pool in pools:
        results[pool] = {
            "status": backup_zpool_status(pool, tracker),
            "properties": backup_zpool_properties(pool, tracker),
        }
    return results


def backup_all_zfs_properties(
    datasets: list[str],
    tracker: HashTracker,
) -> dict[str, bool]:
    """Backup ZFS properties for multiple datasets.

    Args:
        datasets: List of dataset/pool names.
        tracker: HashTracker for change detection.

    Returns:
        Dict mapping dataset to whether it was updated.
    """
    results = {}
    for dataset in datasets:
        results[dataset] = backup_zfs_properties(dataset, tracker)
    return results


# --- Parsing utilities for restore ---


def parse_zfs_properties(content: str) -> dict[str, dict[str, str]]:
    """Parse ZFS properties output into structured data.

    Args:
        content: Output from 'zfs get all'.

    Returns:
        Dict mapping dataset name to dict of property -> value.
    """
    properties: dict[str, dict[str, str]] = {}

    for line in content.strip().split("\n"):
        if not line or line.startswith("NAME"):
            continue

        parts = line.split("\t")
        if len(parts) >= 4:
            dataset = parts[0]
            prop = parts[1]
            value = parts[2]
            source = parts[3]

            if dataset not in properties:
                properties[dataset] = {}

            # Only store local or received properties (not defaults)
            if source in ("local", "received", "-"):
                properties[dataset][prop] = value

    return properties


def parse_zpool_properties(content: str) -> dict[str, str]:
    """Parse zpool properties output into structured data.

    Args:
        content: Output from 'zpool get all'.

    Returns:
        Dict mapping property name to value.
    """
    properties = {}

    for line in content.strip().split("\n"):
        if not line or line.startswith("NAME"):
            continue

        parts = line.split("\t")
        if len(parts) >= 4:
            prop = parts[1]
            value = parts[2]
            source = parts[3]

            # Only store local properties
            if source == "local":
                properties[prop] = value

    return properties


def get_restore_commands(
    zfs_props_file: Path,
    target_pool: str | None = None,
) -> list[str]:
    """Generate ZFS commands to restore properties.

    Args:
        zfs_props_file: Path to ZFS properties backup file.
        target_pool: If specified, replace source pool with this pool name.

    Returns:
        List of 'zfs set' commands.
    """
    if not zfs_props_file.exists():
        return []

    content = zfs_props_file.read_text()
    properties = parse_zfs_properties(content)

    commands = []
    for dataset, props in properties.items():
        # Optionally replace pool name
        if target_pool:
            parts = dataset.split("/", 1)
            if len(parts) > 1:
                dataset = f"{target_pool}/{parts[1]}"
            else:
                dataset = target_pool

        for prop, value in props.items():
            # Skip read-only properties
            if prop in (
                "available", "compressratio", "createtxg", "creation",
                "guid", "logicalreferenced", "logicalused", "objsetid",
                "referenced", "type", "used", "usedbychildren",
                "usedbydataset", "usedbyrefreservation", "usedbysnapshots",
                "written", "mounted", "origin",
            ):
                continue

            commands.append(f"zfs set {prop}={value} {dataset}")

    return commands

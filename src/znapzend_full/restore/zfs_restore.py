"""
ZFS restore operations.

Provides functionality for restoring ZFS pools and datasets.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from ..utils import run_command

logger = logging.getLogger(__name__)


def create_pool(
    name: str,
    vdevs: list[str],
    properties: dict[str, str] | None = None,
    mount_point: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> bool:
    """Create a new ZFS pool.

    Args:
        name: Pool name.
        vdevs: List of vdev specifications (e.g., ["mirror", "/dev/sda", "/dev/sdb"]).
        properties: Pool properties to set.
        mount_point: Alternative root mount point.
        force: Force creation even if devices appear in use.
        dry_run: Only log what would be done.

    Returns:
        True if successful.
    """
    cmd = ["zpool", "create"]

    if force:
        cmd.append("-f")

    if mount_point:
        cmd.extend(["-R", mount_point])

    if properties:
        for key, value in properties.items():
            cmd.extend(["-o", f"{key}={value}"])

    cmd.append(name)
    cmd.extend(vdevs)

    if dry_run:
        logger.info(f"[DRY RUN] Would run: {' '.join(cmd)}")
        return True

    try:
        run_command(cmd)
        logger.info(f"Created pool: {name}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create pool: {e}")
        return False


def destroy_pool(name: str, force: bool = False, dry_run: bool = False) -> bool:
    """Destroy a ZFS pool.

    Args:
        name: Pool name.
        force: Force destruction.
        dry_run: Only log what would be done.

    Returns:
        True if successful.
    """
    cmd = ["zpool", "destroy"]
    if force:
        cmd.append("-f")
    cmd.append(name)

    if dry_run:
        logger.info(f"[DRY RUN] Would run: {' '.join(cmd)}")
        return True

    try:
        run_command(cmd)
        logger.info(f"Destroyed pool: {name}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to destroy pool: {e}")
        return False


def restore_pool(
    status_file: Path,
    target_devices: dict[str, str],
    target_name: str | None = None,
    mount_point: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> bool:
    """Restore a ZFS pool from saved status.

    This parses the zpool status output and recreates the pool
    with the same vdev layout, but allowing device remapping.

    Args:
        status_file: Path to saved zpool status file.
        target_devices: Mapping of original devices to new devices.
        target_name: New pool name (defaults to original).
        mount_point: Alternative root mount point.
        force: Force pool creation.
        dry_run: Only log what would be done.

    Returns:
        True if successful.
    """
    if not status_file.exists():
        logger.error(f"Status file not found: {status_file}")
        return False

    content = status_file.read_text()
    layout = parse_zpool_status(content)

    if not layout:
        logger.error("Failed to parse zpool status")
        return False

    pool_name = target_name or layout["name"]

    # Build vdev list with device remapping
    vdevs = []
    for vdev in layout["vdevs"]:
        vdev_type = vdev.get("type")
        if vdev_type and vdev_type not in ("disk",):
            vdevs.append(vdev_type)

        for device in vdev.get("devices", []):
            # Remap device if specified
            new_device = target_devices.get(device, device)
            vdevs.append(new_device)

    return create_pool(
        pool_name,
        vdevs,
        mount_point=mount_point,
        force=force,
        dry_run=dry_run,
    )


def parse_zpool_status(content: str) -> dict[str, Any] | None:
    """Parse zpool status output.

    Args:
        content: Output from 'zpool status'.

    Returns:
        Dict with parsed layout or None.
    """
    lines = content.strip().split("\n")
    result: dict[str, Any] = {
        "name": "",
        "state": "",
        "vdevs": [],
    }

    current_vdev: dict[str, Any] | None = None
    in_config = False

    for line in lines:
        line = line.rstrip()

        if line.startswith("  pool:"):
            result["name"] = line.split(":", 1)[1].strip()
        elif line.startswith(" state:"):
            result["state"] = line.split(":", 1)[1].strip()
        elif line.strip() == "config:":
            in_config = True
            continue
        elif in_config and line.strip().startswith("NAME"):
            continue  # Skip header
        elif in_config and line.strip():
            # Parse vdev/device line
            parts = line.split()
            if not parts:
                continue

            name = parts[0]
            indent = len(line) - len(line.lstrip())

            if indent <= 8:  # Pool name
                continue
            elif indent <= 16:  # Vdev type (mirror, raidz, etc.)
                if name in ("mirror", "raidz", "raidz1", "raidz2", "raidz3", "spare", "log", "cache"):
                    current_vdev = {"type": name, "devices": []}
                    result["vdevs"].append(current_vdev)
                else:
                    # Single disk vdev
                    current_vdev = {"type": "disk", "devices": [name]}
                    result["vdevs"].append(current_vdev)
            elif current_vdev is not None:  # Device under vdev
                # name is the device path/id
                current_vdev["devices"].append(name)

    return result if result["name"] else None


def restore_dataset(
    source_snapshot: str,
    target_dataset: str,
    ssh_client: Any | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> bool:
    """Restore a dataset from a snapshot.

    Args:
        source_snapshot: Source snapshot name.
        target_dataset: Target dataset to receive into.
        ssh_client: Optional SSH client for remote source.
        force: Force receive (rollback if needed).
        dry_run: Only log what would be done.

    Returns:
        True if successful.
    """
    if dry_run:
        logger.info(f"[DRY RUN] Would restore {source_snapshot} to {target_dataset}")
        return True

    if ssh_client:
        # Remote restore
        result = ssh_client.stream_receive(source_snapshot, target_dataset, force=force)
        if result.returncode != 0:
            logger.error(f"Failed to restore dataset: {result.stderr}")
            return False
        logger.info(f"Restored {source_snapshot} to {target_dataset}")
        return True
    else:
        # Local restore (clone or rollback)
        cmd = ["zfs", "receive"]
        if force:
            cmd.append("-F")
        cmd.append(target_dataset)

        # For local, we'd need to zfs send | zfs receive
        # This is typically done via remote, but could be from local snapshot
        logger.warning("Local restore not fully implemented")
        return False


def set_dataset_properties(
    dataset: str,
    properties: dict[str, str],
    dry_run: bool = False,
) -> bool:
    """Set properties on a dataset.

    Args:
        dataset: Dataset name.
        properties: Properties to set.
        dry_run: Only log what would be done.

    Returns:
        True if successful.
    """
    for prop, value in properties.items():
        cmd = ["zfs", "set", f"{prop}={value}", dataset]

        if dry_run:
            logger.info(f"[DRY RUN] Would run: {' '.join(cmd)}")
            continue

        try:
            run_command(cmd)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to set property {prop}={value}: {e}")
            return False

    logger.info(f"Set properties on {dataset}")
    return True


def apply_properties_from_file(
    props_file: Path,
    target_pool: str | None = None,
    dry_run: bool = False,
) -> bool:
    """Apply ZFS properties from a backup file.

    Args:
        props_file: Path to saved properties file.
        target_pool: Target pool name (if different from source).
        dry_run: Only log what would be done.

    Returns:
        True if successful.
    """
    if not props_file.exists():
        logger.error(f"Properties file not found: {props_file}")
        return False

    content = props_file.read_text()
    properties: dict[str, dict[str, str]] = {}

    for line in content.split("\n"):
        if not line or line.startswith("NAME"):
            continue

        parts = line.split("\t")
        if len(parts) < 4:
            continue

        dataset = parts[0]
        prop = parts[1]
        value = parts[2]
        source = parts[3]

        # Only apply local properties
        if source != "local":
            continue

        # Skip read-only properties
        if prop in (
            "available", "compressratio", "createtxg", "creation",
            "guid", "logicalreferenced", "logicalused", "objsetid",
            "referenced", "type", "used", "usedbychildren",
            "usedbydataset", "usedbyrefreservation", "usedbysnapshots",
            "written", "mounted", "origin",
        ):
            continue

        # Remap pool name if needed
        if target_pool:
            pool_parts = dataset.split("/", 1)
            if len(pool_parts) > 1:
                dataset = f"{target_pool}/{pool_parts[1]}"
            else:
                dataset = target_pool

        if dataset not in properties:
            properties[dataset] = {}
        properties[dataset][prop] = value

    # Apply properties
    success = True
    for dataset, props in properties.items():
        if not set_dataset_properties(dataset, props, dry_run):
            success = False

    return success

"""
Utility functions for znapzend-full.

Provides common functionality for ZFS operations, hashing, and system queries.
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


# --- ZFS Utilities ---


@dataclass
class ZFSDataset:
    """Represents a ZFS dataset."""
    name: str
    mountpoint: str | None
    used: int
    available: int
    referenced: int
    type: str  # 'filesystem', 'volume', 'snapshot'


@dataclass
class ZPoolInfo:
    """Represents a ZFS pool."""
    name: str
    size: int
    allocated: int
    free: int
    health: str
    altroot: str | None


def run_command(
    cmd: list[str],
    capture_output: bool = True,
    check: bool = True,
    timeout: int | None = 300,
) -> subprocess.CompletedProcess:
    """Run a command and return the result.

    Args:
        cmd: Command and arguments.
        capture_output: Whether to capture stdout/stderr.
        check: Whether to raise on non-zero exit.
        timeout: Timeout in seconds.

    Returns:
        CompletedProcess with result.

    Raises:
        subprocess.CalledProcessError: If check=True and command fails.
        subprocess.TimeoutExpired: If command times out.
    """
    logger.debug(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=capture_output,
        text=True,
        check=check,
        timeout=timeout,
    )
    return result


def list_zpools() -> list[ZPoolInfo]:
    """List all ZFS pools on the system.

    Returns:
        List of ZPoolInfo objects.
    """
    try:
        result = run_command([
            "zpool", "list", "-H", "-o",
            "name,size,alloc,free,health,altroot"
        ])
    except subprocess.CalledProcessError:
        return []

    pools = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 5:
            pools.append(ZPoolInfo(
                name=parts[0],
                size=parse_size(parts[1]),
                allocated=parse_size(parts[2]),
                free=parse_size(parts[3]),
                health=parts[4],
                altroot=parts[5] if len(parts) > 5 and parts[5] != "-" else None,
            ))
    return pools


def list_datasets(pool: str | None = None, recursive: bool = True) -> list[ZFSDataset]:
    """List ZFS datasets.

    Args:
        pool: Pool name to list datasets from. If None, lists all.
        recursive: Whether to list recursively.

    Returns:
        List of ZFSDataset objects.
    """
    cmd = ["zfs", "list", "-H", "-o", "name,mountpoint,used,avail,refer,type"]
    if recursive:
        cmd.append("-r")
    if pool:
        cmd.append(pool)

    try:
        result = run_command(cmd)
    except subprocess.CalledProcessError:
        return []

    datasets = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 6:
            datasets.append(ZFSDataset(
                name=parts[0],
                mountpoint=parts[1] if parts[1] != "-" and parts[1] != "none" else None,
                used=parse_size(parts[2]),
                available=parse_size(parts[3]),
                referenced=parse_size(parts[4]),
                type=parts[5],
            ))
    return datasets


def get_zpool_status(pool: str) -> str:
    """Get zpool status output (vdev layout).

    Args:
        pool: Pool name.

    Returns:
        Output of 'zpool status' command.
    """
    result = run_command(["zpool", "status", pool])
    return result.stdout


def get_zpool_properties(pool: str) -> str:
    """Get all zpool properties.

    Args:
        pool: Pool name.

    Returns:
        Output of 'zpool get all' command.
    """
    result = run_command(["zpool", "get", "all", pool])
    return result.stdout


def get_zfs_properties(dataset: str, recursive: bool = True) -> str:
    """Get all ZFS dataset properties.

    Args:
        dataset: Dataset name (or pool name for all datasets).
        recursive: Whether to get properties recursively.

    Returns:
        Output of 'zfs get all' command.
    """
    cmd = ["zfs", "get", "all"]
    if recursive:
        cmd.append("-r")
    cmd.append(dataset)
    result = run_command(cmd)
    return result.stdout


def list_snapshots(dataset: str, recursive: bool = True) -> list[str]:
    """List snapshots for a dataset.

    Args:
        dataset: Dataset name.
        recursive: Whether to list recursively.

    Returns:
        List of snapshot names.
    """
    cmd = ["zfs", "list", "-H", "-t", "snapshot", "-o", "name"]
    if recursive:
        cmd.append("-r")
    cmd.append(dataset)

    try:
        result = run_command(cmd)
    except subprocess.CalledProcessError:
        return []

    return [line for line in result.stdout.strip().split("\n") if line]


def dataset_exists(dataset: str) -> bool:
    """Check if a ZFS dataset exists.

    Args:
        dataset: Dataset name.

    Returns:
        True if dataset exists.
    """
    try:
        run_command(["zfs", "list", "-H", dataset])
        return True
    except subprocess.CalledProcessError:
        return False


def create_dataset(dataset: str, properties: dict[str, str] | None = None) -> None:
    """Create a ZFS dataset.

    Args:
        dataset: Dataset name to create.
        properties: Optional properties to set.
    """
    cmd = ["zfs", "create"]
    if properties:
        for key, value in properties.items():
            cmd.extend(["-o", f"{key}={value}"])
    cmd.append(dataset)
    run_command(cmd)


# --- Partition Utilities ---


def list_block_devices() -> list[dict]:
    """List block devices using lsblk.

    Returns:
        List of device info dictionaries.
    """
    try:
        result = run_command([
            "lsblk", "-J", "-o",
            "NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,PARTTYPE,PARTTYPENAME,UUID,LABEL"
        ])
        import json
        data = json.loads(result.stdout)
        return data.get("blockdevices", [])
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return []


def find_efi_partitions() -> list[str]:
    """Find EFI partitions on the system.

    Returns:
        List of device paths (e.g., ['/dev/nvme0n1p1']).
    """
    efi_partitions = []
    devices = list_block_devices()

    def search_devices(devs: list[dict], parent: str = "") -> None:
        for dev in devs:
            name = dev.get("name", "")
            full_path = f"/dev/{name}"

            # Check if it's an EFI partition by type UUID or mount point
            parttype = dev.get("parttype", "").lower()
            fstype = dev.get("fstype", "")
            mountpoint = dev.get("mountpoint", "")

            # EFI System Partition GUID
            if parttype == "c12a7328-f81f-11d2-ba4b-00a0c93ec93b":
                efi_partitions.append(full_path)
            elif mountpoint and "/boot/efi" in mountpoint.lower():
                efi_partitions.append(full_path)
            elif fstype == "vfat" and "efi" in name.lower():
                efi_partitions.append(full_path)

            # Recurse into children
            children = dev.get("children", [])
            if children:
                search_devices(children, full_path)

    search_devices(devices)
    return efi_partitions


def find_gpt_disks() -> list[str]:
    """Find disks with GPT partition tables.

    Returns:
        List of disk device paths.
    """
    gpt_disks = []
    try:
        result = run_command(["lsblk", "-d", "-n", "-o", "NAME,TYPE"])
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "disk":
                disk = f"/dev/{parts[0]}"
                # Check if it has a GPT
                try:
                    sgdisk_result = run_command(
                        ["sgdisk", "-v", disk],
                        check=False
                    )
                    if sgdisk_result.returncode == 0:
                        gpt_disks.append(disk)
                except subprocess.CalledProcessError:
                    pass
    except subprocess.CalledProcessError:
        pass
    return gpt_disks


def backup_gpt(disk: str, output_path: Path) -> None:
    """Backup GPT partition table.

    Args:
        disk: Disk device path.
        output_path: Path for binary backup file.
    """
    run_command(["sgdisk", "--backup", str(output_path), disk])


def backup_gpt_readable(disk: str, output_path: Path) -> None:
    """Backup GPT partition table in human-readable format.

    Args:
        disk: Disk device path.
        output_path: Path for text backup file.
    """
    result = run_command(["sgdisk", "--print", disk])
    output_path.write_text(result.stdout)


def backup_efi(partition: str, output_path: Path) -> None:
    """Backup EFI partition using dd.

    Args:
        partition: Partition device path.
        output_path: Path for image file.
    """
    run_command([
        "dd",
        f"if={partition}",
        f"of={output_path}",
        "bs=4M",
        "status=none"
    ])


# --- Hash Utilities ---


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file.

    Args:
        file_path: Path to file.

    Returns:
        Hex digest of SHA256 hash.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_sha256_string(content: str) -> str:
    """Compute SHA256 hash of a string.

    Args:
        content: String content.

    Returns:
        Hex digest of SHA256 hash.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def hash_matches(file_path: Path, hash_path: Path) -> bool:
    """Check if a file's hash matches the stored hash.

    Args:
        file_path: Path to file.
        hash_path: Path to hash file.

    Returns:
        True if hashes match, False otherwise.
    """
    if not file_path.exists() or not hash_path.exists():
        return False

    current_hash = compute_sha256(file_path)
    stored_hash = hash_path.read_text().strip().split()[0]  # Handle "hash  filename" format
    return current_hash == stored_hash


def save_hash(file_path: Path, hash_path: Path) -> None:
    """Compute and save hash for a file.

    Args:
        file_path: Path to file.
        hash_path: Path to save hash.
    """
    file_hash = compute_sha256(file_path)
    hash_path.write_text(f"{file_hash}  {file_path.name}\n")


# --- Size Parsing ---


def parse_size(size_str: str) -> int:
    """Parse a size string (e.g., '1.5G', '500M') to bytes.

    Args:
        size_str: Size string.

    Returns:
        Size in bytes.
    """
    if not size_str or size_str == "-":
        return 0

    size_str = size_str.strip().upper()
    multipliers = {
        "B": 1,
        "K": 1024,
        "M": 1024 ** 2,
        "G": 1024 ** 3,
        "T": 1024 ** 4,
        "P": 1024 ** 5,
    }

    for suffix, multiplier in multipliers.items():
        if size_str.endswith(suffix):
            try:
                return int(float(size_str[:-1]) * multiplier)
            except ValueError:
                return 0

    try:
        return int(size_str)
    except ValueError:
        return 0


def format_size(size_bytes: int) -> str:
    """Format bytes to human-readable size.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Human-readable size string.
    """
    for unit in ["B", "K", "M", "G", "T", "P"]:
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}E"


# --- Logging Setup ---


def setup_logging(
    level: int = logging.INFO,
    log_file: Path | None = None,
) -> None:
    """Set up logging configuration.

    Args:
        level: Logging level.
        log_file: Optional log file path.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )

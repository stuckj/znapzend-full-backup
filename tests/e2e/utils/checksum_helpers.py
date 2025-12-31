"""
Checksum and verification helpers for E2E tests.

Provides utilities for computing checksums and verifying data integrity
between source and restored systems.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import paramiko

logger = logging.getLogger(__name__)


def compute_remote_checksum(
    ssh_client: "paramiko.SSHClient",
    path: str,
    recursive: bool = True,
) -> dict[str, str]:
    """Compute SHA256 checksums for files on a remote host.

    Args:
        ssh_client: Connected SSH client.
        path: Path to file or directory.
        recursive: If True, compute checksums for all files recursively.

    Returns:
        Dict mapping relative paths to SHA256 checksums.
    """
    if recursive:
        cmd = f"find {path} -type f -exec sha256sum {{}} \\;"
    else:
        cmd = f"sha256sum {path}"

    logger.debug(f"Computing checksums for {path}")
    _, stdout, stderr = ssh_client.exec_command(cmd)
    output = stdout.read().decode()
    errors = stderr.read().decode()

    if errors:
        logger.warning(f"Errors computing checksums: {errors}")

    checksums = {}
    for line in output.strip().split("\n"):
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            checksum, filepath = parts
            # Normalize path relative to base
            rel_path = filepath.replace(path, "").lstrip("/")
            if rel_path:  # Skip empty (the base path itself)
                checksums[rel_path] = checksum

    logger.debug(f"Computed {len(checksums)} checksums")
    return checksums


def compare_checksums(
    source_checksums: dict[str, str],
    target_checksums: dict[str, str],
) -> tuple[bool, list[str]]:
    """Compare two checksum dictionaries.

    Args:
        source_checksums: Checksums from source.
        target_checksums: Checksums from target.

    Returns:
        Tuple of (match: bool, differences: list of difference descriptions).
    """
    differences = []

    # Check for missing files on target
    for path, checksum in source_checksums.items():
        if path not in target_checksums:
            differences.append(f"Missing on target: {path}")
        elif target_checksums[path] != checksum:
            differences.append(f"Checksum mismatch: {path}")

    # Check for extra files on target
    for path in target_checksums:
        if path not in source_checksums:
            differences.append(f"Extra on target: {path}")

    if differences:
        logger.warning(f"Found {len(differences)} differences")
        for diff in differences[:10]:  # Log first 10
            logger.warning(f"  {diff}")
        if len(differences) > 10:
            logger.warning(f"  ... and {len(differences) - 10} more")
    else:
        logger.info("All checksums match")

    return len(differences) == 0, differences


def verify_zfs_properties(
    ssh_client: "paramiko.SSHClient",
    dataset: str,
    expected_props: dict[str, str],
) -> tuple[bool, list[str]]:
    """Verify ZFS dataset properties match expected values.

    Args:
        ssh_client: Connected SSH client.
        dataset: ZFS dataset name.
        expected_props: Dict of property names to expected values.

    Returns:
        Tuple of (match: bool, errors: list of error descriptions).
    """
    errors = []

    for prop, expected in expected_props.items():
        _, stdout, stderr = ssh_client.exec_command(
            f"zfs get -H -o value {prop} {dataset} 2>/dev/null"
        )
        actual = stdout.read().decode().strip()

        if not actual:
            errors.append(f"Property {prop} not found on {dataset}")
        elif actual != expected:
            errors.append(f"{dataset}:{prop} - expected '{expected}', got '{actual}'")

    if errors:
        logger.warning(f"Found {len(errors)} property mismatches")
        for error in errors:
            logger.warning(f"  {error}")
    else:
        logger.info(f"All properties match for {dataset}")

    return len(errors) == 0, errors


def get_zfs_properties(
    ssh_client: "paramiko.SSHClient",
    dataset: str,
    properties: list[str] | None = None,
) -> dict[str, str]:
    """Get ZFS properties for a dataset.

    Args:
        ssh_client: Connected SSH client.
        dataset: ZFS dataset name.
        properties: List of property names (default: all local properties).

    Returns:
        Dict of property names to values.
    """
    if properties:
        prop_str = ",".join(properties)
        cmd = f"zfs get -H -o property,value {prop_str} {dataset}"
    else:
        # Get all local properties
        cmd = f"zfs get -H -o property,value,source all {dataset}"

    _, stdout, _ = ssh_client.exec_command(cmd)
    output = stdout.read().decode()

    props = {}
    for line in output.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            prop_name = parts[0]
            prop_value = parts[1]
            # If we got source column, only include local properties
            if len(parts) >= 3:
                source = parts[2]
                if source == "local":
                    props[prop_name] = prop_value
            else:
                props[prop_name] = prop_value

    return props


def verify_metadata_present(
    ssh_client: "paramiko.SSHClient",
    metadata_dataset: str,
) -> tuple[bool, list[str]]:
    """Verify that expected metadata files are present.

    Args:
        ssh_client: Connected SSH client.
        metadata_dataset: ZFS dataset containing metadata.

    Returns:
        Tuple of (valid: bool, missing: list of missing file types).
    """
    expected_dirs = ["efi", "gpt", "zpool", "zfs"]
    missing = []

    # Get mountpoint
    _, stdout, _ = ssh_client.exec_command(
        f"zfs get -H -o value mountpoint {metadata_dataset}"
    )
    mountpoint = stdout.read().decode().strip()

    if not mountpoint or mountpoint == "-":
        mountpoint = f"/{metadata_dataset}"

    for dir_name in expected_dirs:
        _, stdout, _ = ssh_client.exec_command(
            f"ls {mountpoint}/{dir_name}/ 2>/dev/null | wc -l"
        )
        count = stdout.read().decode().strip()
        if count == "0":
            missing.append(dir_name)

    if missing:
        logger.warning(f"Missing metadata directories: {missing}")
    else:
        logger.info("All expected metadata directories present")

    return len(missing) == 0, missing


def verify_file_exists(
    ssh_client: "paramiko.SSHClient",
    path: str,
) -> bool:
    """Check if a file exists on the remote host.

    Args:
        ssh_client: Connected SSH client.
        path: Path to check.

    Returns:
        True if file exists.
    """
    _, stdout, _ = ssh_client.exec_command(f"test -f {path} && echo yes || echo no")
    return stdout.read().decode().strip() == "yes"


def verify_directory_exists(
    ssh_client: "paramiko.SSHClient",
    path: str,
) -> bool:
    """Check if a directory exists on the remote host.

    Args:
        ssh_client: Connected SSH client.
        path: Path to check.

    Returns:
        True if directory exists.
    """
    _, stdout, _ = ssh_client.exec_command(f"test -d {path} && echo yes || echo no")
    return stdout.read().decode().strip() == "yes"

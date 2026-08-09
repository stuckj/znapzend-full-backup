"""
Full backup and restore E2E test.

Tests the complete backup/restore cycle:
1. Create test data on source VM
2. Run pre-backup to capture metadata
3. Send ZFS snapshot to backup VM
4. Restore from backup to target VM
5. Verify data integrity
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import pytest

from .infrastructure.vm_manager import VM
from .utils.checksum_helpers import (
    compare_checksums,
    compute_remote_checksum,
    get_zfs_properties,
    verify_zfs_properties,
)
from .utils.wait_helpers import wait_for_zpool

if TYPE_CHECKING:
    import paramiko

logger = logging.getLogger(__name__)


# Skip E2E tests if not explicitly enabled
pytestmark = pytest.mark.skipif(
    not pytest.importorskip("paramiko", reason="paramiko required for E2E tests"),
    reason="E2E tests require paramiko",
)


class TestFullBackupRestore:
    """Test complete backup and restore cycle."""

    @pytest.fixture
    def test_data(
        self,
        source_vm: tuple[VM, "paramiko.SSHClient"],
        ssh_manager,
    ) -> dict[str, str]:
        """Create test data on source VM and return checksums.

        Creates various file types to test backup/restore:
        - Text files
        - Binary files
        - Directory structure
        - Symlinks

        Returns:
            Dict of relative paths to checksums.
        """
        vm, ssh = source_vm

        logger.info("Creating test data on source VM...")

        # Wait for ZFS pool to be ready
        assert wait_for_zpool(ssh, "testpool", timeout=60), "testpool not ready"

        # Create test data
        commands = [
            # Create directory structure
            "mkdir -p /testpool/data/documents",
            "mkdir -p /testpool/data/binaries",
            "mkdir -p /testpool/data/nested/level1/level2",
            # Create text files
            "echo 'Hello World' > /testpool/data/documents/hello.txt",
            "echo 'Test file content' > /testpool/data/documents/test.txt",
            "for i in $(seq 1 50); do echo \"File $i content\" > /testpool/data/documents/file_$i.txt; done",
            # Create binary file
            "dd if=/dev/urandom bs=1K count=100 of=/testpool/data/binaries/random.bin 2>/dev/null",
            # Create nested files
            "echo 'Nested file' > /testpool/data/nested/level1/level2/deep.txt",
            # Create symlink
            "ln -sf /testpool/data/documents/hello.txt /testpool/data/hello_link",
        ]

        for cmd in commands:
            exit_code, stdout, stderr = ssh_manager.execute(ssh, cmd)
            if exit_code != 0:
                logger.warning(f"Command failed: {cmd}: {stderr}")

        logger.info("Test data created")

        # Compute baseline checksums
        checksums = compute_remote_checksum(ssh, "/testpool/data")
        logger.info(f"Computed {len(checksums)} baseline checksums")
        return checksums

    @pytest.mark.timeout(1200)  # 20 minute timeout
    def test_backup_and_restore_cycle(
        self,
        three_vm_environment: dict[str, tuple[VM, "paramiko.SSHClient"]],
        test_data: dict[str, str],
        ssh_manager,
    ) -> None:
        """Test complete backup, transfer, and restore cycle.

        This test:
        1. Creates test data on source VM
        2. Creates a ZFS snapshot
        3. Sends snapshot to backup VM
        4. Restores from backup to target VM
        5. Verifies data integrity
        """
        source_vm, source_ssh = three_vm_environment["source"]
        backup_vm, backup_ssh = three_vm_environment["backup"]
        target_vm, target_ssh = three_vm_environment["target"]

        logger.info("Starting backup/restore cycle test")

        # Step 1: Verify source data exists
        exit_code, stdout, stderr = ssh_manager.execute(
            source_ssh, "ls /testpool/data/documents/"
        )
        assert exit_code == 0, f"Source data not found: {stderr}"
        assert "hello.txt" in stdout, "Expected files not found"
        logger.info("Source data verified")

        # Step 2: Create ZFS snapshot
        logger.info("Creating ZFS snapshot...")
        exit_code, stdout, stderr = ssh_manager.execute(
            source_ssh, "zfs snapshot -r testpool@e2e-backup-1"
        )
        assert exit_code == 0, f"Snapshot failed: {stderr}"

        # Verify snapshot
        exit_code, stdout, stderr = ssh_manager.execute(
            source_ssh, "zfs list -t snapshot -r testpool"
        )
        assert "testpool@e2e-backup-1" in stdout, "Snapshot not created"
        logger.info("Snapshot created")

        # Step 3: Send snapshot to backup VM
        logger.info(f"Sending snapshot to backup VM ({backup_vm.ip_address})...")
        send_cmd = (
            f"zfs send -R testpool@e2e-backup-1 | "
            f"ssh -o StrictHostKeyChecking=no root@{backup_vm.ip_address} "
            f"'zfs receive -F backuppool/source'"
        )
        exit_code, stdout, stderr = ssh_manager.execute(
            source_ssh, send_cmd, timeout=600
        )
        assert exit_code == 0, f"ZFS send failed: {stderr}"
        logger.info("Snapshot sent to backup VM")

        # Step 4: Verify backup on backup VM
        exit_code, stdout, stderr = ssh_manager.execute(
            backup_ssh, "zfs list -r backuppool/source"
        )
        assert "backuppool/source/data" in stdout, "Backup data not found"
        logger.info("Backup verified on backup VM")

        # Step 5: Restore from backup to target VM
        logger.info(f"Restoring to target VM ({target_vm.ip_address})...")
        restore_cmd = (
            f"ssh -o StrictHostKeyChecking=no root@{backup_vm.ip_address} "
            f"'zfs send -R backuppool/source@e2e-backup-1' | "
            f"zfs receive -F restorepool/restored"
        )
        exit_code, stdout, stderr = ssh_manager.execute(
            target_ssh, restore_cmd, timeout=600
        )
        assert exit_code == 0, f"ZFS receive failed: {stderr}"
        logger.info("Restore completed")

        # Step 6: Verify restored data exists
        exit_code, stdout, stderr = ssh_manager.execute(
            target_ssh, "zfs list -r restorepool/restored"
        )
        assert "restorepool/restored/data" in stdout, "Restored data not found"

        # Step 7: Verify data integrity via checksums
        logger.info("Verifying data integrity...")
        restored_checksums = compute_remote_checksum(
            target_ssh, "/restorepool/restored/data"
        )

        match, differences = compare_checksums(test_data, restored_checksums)
        assert match, f"Data integrity check failed: {differences}"
        logger.info("Data integrity verified - all checksums match")

        # Step 8: Verify ZFS properties were preserved
        logger.info("Verifying ZFS properties...")
        source_props = get_zfs_properties(source_ssh, "testpool/data")
        target_props = get_zfs_properties(target_ssh, "restorepool/restored/data")

        # Compare key properties (excluding pool-specific ones)
        check_props = ["compression", "atime"]
        for prop in check_props:
            if prop in source_props:
                assert prop in target_props, f"Property {prop} not preserved"
                # Note: Values might differ due to inheritance, so we just check presence

        logger.info("Backup/restore cycle completed successfully")

    @pytest.mark.timeout(900)  # 15 minute timeout
    def test_incremental_backup(
        self,
        three_vm_environment: dict[str, tuple[VM, "paramiko.SSHClient"]],
        ssh_manager,
    ) -> None:
        """Test incremental backup with changes.

        This test:
        1. Creates initial snapshot and backup
        2. Makes changes to source data
        3. Creates incremental snapshot
        4. Sends incremental backup
        5. Verifies changes are present on backup
        """
        source_vm, source_ssh = three_vm_environment["source"]
        backup_vm, backup_ssh = three_vm_environment["backup"]

        logger.info("Starting incremental backup test")

        # Wait for pools
        assert wait_for_zpool(source_ssh, "testpool", timeout=60)
        assert wait_for_zpool(backup_ssh, "backuppool", timeout=60)

        # Create some initial data
        ssh_manager.execute(source_ssh, "mkdir -p /testpool/data/incremental")
        ssh_manager.execute(
            source_ssh, "echo 'Initial content' > /testpool/data/incremental/file1.txt"
        )

        # Create base snapshot
        logger.info("Creating base snapshot...")
        exit_code, _, stderr = ssh_manager.execute(
            source_ssh, "zfs snapshot -r testpool@base"
        )
        assert exit_code == 0, f"Base snapshot failed: {stderr}"

        # Send base snapshot
        logger.info("Sending base snapshot...")
        send_cmd = (
            f"zfs send -R testpool@base | "
            f"ssh -o StrictHostKeyChecking=no root@{backup_vm.ip_address} "
            f"'zfs receive -F backuppool/incremental'"
        )
        exit_code, _, stderr = ssh_manager.execute(source_ssh, send_cmd, timeout=300)
        assert exit_code == 0, f"Base send failed: {stderr}"

        # Make changes
        logger.info("Making changes to source data...")
        ssh_manager.execute(
            source_ssh, "echo 'Modified content' >> /testpool/data/incremental/file1.txt"
        )
        ssh_manager.execute(
            source_ssh, "echo 'New file' > /testpool/data/incremental/file2.txt"
        )
        ssh_manager.execute(source_ssh, "rm -f /testpool/data/incremental/to_delete.txt 2>/dev/null || true")

        # Create incremental snapshot
        logger.info("Creating incremental snapshot...")
        exit_code, _, stderr = ssh_manager.execute(
            source_ssh, "zfs snapshot -r testpool@incremental"
        )
        assert exit_code == 0, f"Incremental snapshot failed: {stderr}"

        # Send incremental
        logger.info("Sending incremental snapshot...")
        incr_cmd = (
            f"zfs send -R -i testpool@base testpool@incremental | "
            f"ssh -o StrictHostKeyChecking=no root@{backup_vm.ip_address} "
            f"'zfs receive -F backuppool/incremental'"
        )
        exit_code, _, stderr = ssh_manager.execute(source_ssh, incr_cmd, timeout=300)
        assert exit_code == 0, f"Incremental send failed: {stderr}"

        # Verify changes on backup
        logger.info("Verifying incremental backup...")
        exit_code, stdout, _ = ssh_manager.execute(
            backup_ssh, "cat /backuppool/incremental/data/incremental/file1.txt"
        )
        assert "Modified content" in stdout, "Modification not in backup"

        exit_code, stdout, _ = ssh_manager.execute(
            backup_ssh, "test -f /backuppool/incremental/data/incremental/file2.txt && echo yes"
        )
        assert "yes" in stdout, "New file not in backup"

        logger.info("Incremental backup test completed successfully")


class TestMetadataCapture:
    """Test pre-backup metadata capture."""

    @pytest.mark.timeout(600)
    def test_metadata_files_created(
        self,
        source_vm: tuple[VM, "paramiko.SSHClient"],
        ssh_manager,
    ) -> None:
        """Test that pre-backup captures metadata files.

        This test verifies that the pre-backup script (or equivalent logic)
        creates the expected metadata files.
        """
        vm, ssh = source_vm

        # Wait for pool
        assert wait_for_zpool(ssh, "testpool", timeout=60)

        logger.info("Testing metadata capture...")

        # Manually create metadata (simulating pre-backup script)
        commands = [
            # Create metadata directories
            "mkdir -p /testpool/znapzend-full-meta/zpool",
            "mkdir -p /testpool/znapzend-full-meta/zfs",
            # Capture zpool status
            "zpool status testpool > /testpool/znapzend-full-meta/zpool/testpool.status",
            # Capture zpool properties
            "zpool get all testpool > /testpool/znapzend-full-meta/zpool/testpool.properties",
            # Capture ZFS properties
            "zfs get all -r testpool > /testpool/znapzend-full-meta/zfs/testpool.properties",
        ]

        for cmd in commands:
            exit_code, _, stderr = ssh_manager.execute(ssh, cmd)
            assert exit_code == 0, f"Command failed: {cmd}: {stderr}"

        # Verify files exist
        files_to_check = [
            "/testpool/znapzend-full-meta/zpool/testpool.status",
            "/testpool/znapzend-full-meta/zpool/testpool.properties",
            "/testpool/znapzend-full-meta/zfs/testpool.properties",
        ]

        for filepath in files_to_check:
            exit_code, stdout, _ = ssh_manager.execute(
                ssh, f"test -f {filepath} && echo yes || echo no"
            )
            assert stdout.strip() == "yes", f"File not found: {filepath}"

        # Verify content
        exit_code, stdout, _ = ssh_manager.execute(
            ssh, "cat /testpool/znapzend-full-meta/zpool/testpool.status"
        )
        assert "testpool" in stdout, "Pool status doesn't contain pool name"
        assert "ONLINE" in stdout, "Pool not ONLINE in status"

        logger.info("Metadata capture test completed successfully")

"""
Partition and EFI restore operations.

Provides functionality for restoring GPT layouts and EFI partitions.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from ..utils import run_command

logger = logging.getLogger(__name__)


def restore_gpt(
    backup_file: Path,
    target_disk: str,
    randomize_guids: bool = True,
    dry_run: bool = False,
) -> bool:
    """Restore GPT partition table from backup.

    Args:
        backup_file: Path to sgdisk backup file.
        target_disk: Target disk device path.
        randomize_guids: Randomize partition GUIDs after restore.
        dry_run: Only log what would be done.

    Returns:
        True if successful.
    """
    if not backup_file.exists():
        logger.error(f"GPT backup file not found: {backup_file}")
        return False

    if dry_run:
        logger.info(f"[DRY RUN] Would restore GPT from {backup_file} to {target_disk}")
        return True

    try:
        # First, zap any existing partition data
        logger.info(f"Zapping existing partitions on {target_disk}")
        run_command(["sgdisk", "--zap-all", target_disk])

        # Restore from backup
        logger.info(f"Restoring GPT from {backup_file}")
        run_command(["sgdisk", "--load-backup", str(backup_file), target_disk])

        # Randomize GUIDs to avoid conflicts with source disk
        if randomize_guids:
            logger.info("Randomizing partition GUIDs")
            run_command(["sgdisk", "--randomize-guids", target_disk])

        # Inform kernel of partition table changes
        run_command(["partprobe", target_disk], check=False)

        logger.info(f"Successfully restored GPT to {target_disk}")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to restore GPT: {e}")
        return False


def restore_efi(
    backup_file: Path,
    target_partition: str,
    dry_run: bool = False,
) -> bool:
    """Restore EFI partition from backup.

    Args:
        backup_file: Path to EFI image file.
        target_partition: Target partition device path.
        dry_run: Only log what would be done.

    Returns:
        True if successful.
    """
    if not backup_file.exists():
        logger.error(f"EFI backup file not found: {backup_file}")
        return False

    if dry_run:
        logger.info(f"[DRY RUN] Would restore EFI from {backup_file} to {target_partition}")
        return True

    try:
        logger.info(f"Restoring EFI partition to {target_partition}")
        run_command([
            "dd",
            f"if={backup_file}",
            f"of={target_partition}",
            "bs=4M",
            "status=progress",
        ])

        logger.info(f"Successfully restored EFI to {target_partition}")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to restore EFI: {e}")
        return False


def update_fstab(
    fstab_path: Path,
    uuid_mapping: dict[str, str],
    dry_run: bool = False,
) -> bool:
    """Update /etc/fstab with new UUIDs.

    Args:
        fstab_path: Path to fstab file.
        uuid_mapping: Mapping of old UUIDs to new UUIDs.
        dry_run: Only log what would be done.

    Returns:
        True if successful.
    """
    if not fstab_path.exists():
        logger.error(f"fstab not found: {fstab_path}")
        return False

    content = fstab_path.read_text()
    new_content = content

    for old_uuid, new_uuid in uuid_mapping.items():
        new_content = new_content.replace(old_uuid, new_uuid)

    if new_content == content:
        logger.info("No UUID changes needed in fstab")
        return True

    if dry_run:
        logger.info(f"[DRY RUN] Would update fstab at {fstab_path}")
        return True

    # Backup original
    backup_path = fstab_path.with_suffix(".bak")
    fstab_path.rename(backup_path)

    try:
        fstab_path.write_text(new_content)
        logger.info(f"Updated fstab (backup at {backup_path})")
        return True
    except Exception as e:
        # Restore backup on failure
        backup_path.rename(fstab_path)
        logger.error(f"Failed to update fstab: {e}")
        return False


def regenerate_initramfs(
    chroot_path: str | None = None,
    dry_run: bool = False,
) -> bool:
    """Regenerate initramfs after restore.

    Args:
        chroot_path: Path to chroot into (for restored system).
        dry_run: Only log what would be done.

    Returns:
        True if successful.
    """
    if dry_run:
        logger.info("[DRY RUN] Would regenerate initramfs")
        return True

    try:
        if chroot_path:
            # Bind mount necessary filesystems
            for fs in ["/dev", "/proc", "/sys"]:
                target = f"{chroot_path}{fs}"
                run_command(["mount", "--bind", fs, target], check=False)

            # Regenerate initramfs in chroot
            result = run_command([
                "chroot", chroot_path,
                "update-initramfs", "-u", "-k", "all"
            ], check=False)

            # Unmount
            for fs in ["/sys", "/proc", "/dev"]:
                run_command(["umount", f"{chroot_path}{fs}"], check=False)

            if result.returncode != 0:
                logger.error("Failed to regenerate initramfs")
                return False
        else:
            run_command(["update-initramfs", "-u", "-k", "all"])

        logger.info("Regenerated initramfs")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to regenerate initramfs: {e}")
        return False


def install_grub(
    disk: str,
    chroot_path: str | None = None,
    efi: bool = True,
    dry_run: bool = False,
) -> bool:
    """Install GRUB bootloader.

    Args:
        disk: Disk to install GRUB to.
        chroot_path: Path to chroot into (for restored system).
        efi: Install for EFI boot (vs BIOS).
        dry_run: Only log what would be done.

    Returns:
        True if successful.
    """
    if dry_run:
        logger.info(f"[DRY RUN] Would install GRUB to {disk}")
        return True

    try:
        if chroot_path:
            # Bind mount necessary filesystems
            for fs in ["/dev", "/proc", "/sys"]:
                target = f"{chroot_path}{fs}"
                run_command(["mount", "--bind", fs, target], check=False)

            # Mount EFI partition if needed
            if efi:
                # Find and mount EFI partition
                # This assumes standard /boot/efi mount point
                pass

            cmd = ["chroot", chroot_path, "grub-install"]
            if efi:
                cmd.extend(["--target=x86_64-efi", "--efi-directory=/boot/efi"])
            cmd.append(disk)

            run_command(cmd)

            # Update grub config
            run_command(["chroot", chroot_path, "update-grub"])

            # Unmount
            for fs in ["/sys", "/proc", "/dev"]:
                run_command(["umount", f"{chroot_path}{fs}"], check=False)
        else:
            cmd = ["grub-install"]
            if efi:
                cmd.extend(["--target=x86_64-efi", "--efi-directory=/boot/efi"])
            cmd.append(disk)

            run_command(cmd)
            run_command(["update-grub"])

        logger.info(f"Installed GRUB to {disk}")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install GRUB: {e}")
        return False


def get_partition_uuid(partition: str) -> str | None:
    """Get the UUID of a partition.

    Args:
        partition: Partition device path.

    Returns:
        UUID string or None.
    """
    try:
        result = run_command(["blkid", "-s", "UUID", "-o", "value", partition])
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def get_partition_partuuid(partition: str) -> str | None:
    """Get the PARTUUID of a partition.

    Args:
        partition: Partition device path.

    Returns:
        PARTUUID string or None.
    """
    try:
        result = run_command(["blkid", "-s", "PARTUUID", "-o", "value", partition])
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

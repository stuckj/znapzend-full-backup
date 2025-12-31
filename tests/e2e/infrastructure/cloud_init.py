"""
Cloud-init configuration generation for E2E tests.

Provides functionality to generate cloud-init ISO images for configuring
test VMs on boot.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CloudInitGenerator:
    """Generates cloud-init configuration for test VMs."""

    work_dir: Path
    ssh_public_key: str
    gateway: str = "10.100.0.1"
    nameserver: str = "8.8.8.8"

    def __post_init__(self) -> None:
        """Initialize work directory."""
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def generate_iso(
        self,
        vm_name: str,
        role: str,
        ip_address: str,
        extra_config: dict[str, Any] | None = None,
    ) -> Path:
        """Generate a cloud-init ISO for a VM.

        Args:
            vm_name: Name of the VM.
            role: VM role (source, backup, target).
            ip_address: Static IP address for the VM.
            extra_config: Additional cloud-init configuration.

        Returns:
            Path to the generated ISO.
        """
        iso_dir = self.work_dir / vm_name
        iso_dir.mkdir(parents=True, exist_ok=True)

        # Generate configuration files
        meta_data = self._generate_meta_data(vm_name)
        user_data = self._generate_user_data(vm_name, role, extra_config)
        network_config = self._generate_network_config(ip_address)

        # Write configuration files
        (iso_dir / "meta-data").write_text(meta_data)
        (iso_dir / "user-data").write_text(user_data)
        (iso_dir / "network-config").write_text(network_config)

        # Generate ISO
        iso_path = self.work_dir / f"{vm_name}-cloud-init.iso"
        self._create_iso(iso_dir, iso_path)

        logger.info(f"Generated cloud-init ISO: {iso_path}")
        return iso_path

    def _generate_meta_data(self, vm_name: str) -> str:
        """Generate meta-data content."""
        return f"""instance-id: {vm_name}
local-hostname: {vm_name}
"""

    def _generate_user_data(
        self,
        vm_name: str,
        role: str,
        extra_config: dict[str, Any] | None = None,
    ) -> str:
        """Generate user-data content based on VM role."""
        # Base configuration
        config = {
            "hostname": vm_name,
            "users": [
                {
                    "name": "root",
                    "ssh_authorized_keys": [self.ssh_public_key],
                    "lock_passwd": True,
                }
            ],
            "package_update": True,
            "packages": ["zfsutils-linux", "sgdisk", "python3-pip"],
            "runcmd": [],
            "write_files": [],
        }

        # Role-specific configuration
        if role == "source":
            config["runcmd"].extend(self._source_vm_commands())
            config["write_files"].extend(self._source_vm_files())
        elif role == "backup":
            config["runcmd"].extend(self._backup_vm_commands())
        elif role == "target":
            config["runcmd"].extend(self._target_vm_commands())

        # Common final commands
        config["runcmd"].append("touch /var/run/e2e-ready")

        # Merge extra config
        if extra_config:
            for key, value in extra_config.items():
                if isinstance(value, list) and key in config:
                    config[key].extend(value)
                else:
                    config[key] = value

        return self._to_cloud_config(config)

    def _source_vm_commands(self) -> list[str]:
        """Commands for source VM setup."""
        return [
            # Create file-backed ZFS pool
            "truncate -s 2G /tmp/zfs-disk.img",
            "zpool create -f testpool /tmp/zfs-disk.img",
            # Create datasets
            "zfs create testpool/ROOT",
            "zfs create testpool/data",
            "zfs create testpool/znapzend-full-meta",
            # Set some properties
            "zfs set compression=lz4 testpool",
            "zfs set atime=off testpool/data",
        ]

    def _source_vm_files(self) -> list[dict]:
        """Files to write on source VM."""
        return [
            {
                "path": "/etc/modprobe.d/zfs.conf",
                "content": "options zfs zfs_arc_max=268435456\n",
            },
        ]

    def _backup_vm_commands(self) -> list[str]:
        """Commands for backup VM setup."""
        return [
            # Create file-backed ZFS pool for receiving backups
            "truncate -s 4G /tmp/backup-disk.img",
            "zpool create -f backuppool /tmp/backup-disk.img",
            # Create directory for backups
            "zfs create backuppool/backups",
        ]

    def _target_vm_commands(self) -> list[str]:
        """Commands for target VM setup."""
        return [
            # Create file-backed ZFS pool for restore target
            "truncate -s 2G /tmp/restore-disk.img",
            "zpool create -f restorepool /tmp/restore-disk.img",
        ]

    def _generate_network_config(self, ip_address: str) -> str:
        """Generate network-config content."""
        return f"""version: 2
ethernets:
  eth0:
    match:
      driver: virtio
    addresses:
      - {ip_address}/24
    gateway4: {self.gateway}
    nameservers:
      addresses:
        - {self.nameserver}
"""

    def _to_cloud_config(self, config: dict) -> str:
        """Convert config dict to cloud-config YAML."""
        import yaml

        # Start with cloud-config header
        content = "#cloud-config\n"
        content += yaml.dump(config, default_flow_style=False, sort_keys=False)
        return content

    def _create_iso(self, source_dir: Path, iso_path: Path) -> None:
        """Create an ISO from a directory using cloud-localds or genisoimage."""
        # Try cloud-localds first (preferred)
        try:
            subprocess.run(
                [
                    "cloud-localds",
                    "--network-config",
                    str(source_dir / "network-config"),
                    str(iso_path),
                    str(source_dir / "user-data"),
                    str(source_dir / "meta-data"),
                ],
                check=True,
                capture_output=True,
            )
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        # Fall back to genisoimage
        try:
            subprocess.run(
                [
                    "genisoimage",
                    "-output",
                    str(iso_path),
                    "-volid",
                    "cidata",
                    "-joliet",
                    "-rock",
                    str(source_dir / "user-data"),
                    str(source_dir / "meta-data"),
                    str(source_dir / "network-config"),
                ],
                check=True,
                capture_output=True,
            )
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        # Fall back to mkisofs
        subprocess.run(
            [
                "mkisofs",
                "-output",
                str(iso_path),
                "-volid",
                "cidata",
                "-joliet",
                "-rock",
                str(source_dir / "user-data"),
                str(source_dir / "meta-data"),
                str(source_dir / "network-config"),
            ],
            check=True,
            capture_output=True,
        )

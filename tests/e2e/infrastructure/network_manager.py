"""
Virtual network management for E2E tests.

Provides functionality to create and manage a virtual bridge network
for VM-to-VM communication during E2E tests.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class VirtualNetworkManager:
    """Manages virtual networking for E2E test VMs."""

    bridge_name: str = "znapzend-e2e-br0"
    subnet: str = "10.100.0.0/24"
    gateway: str = "10.100.0.1"
    tap_devices: dict[str, str] = field(default_factory=dict)
    _bridge_created: bool = False

    def setup_bridge(self) -> None:
        """Create and configure the virtual bridge.

        Creates a Linux bridge for VM networking with NAT for internet access.
        Requires root privileges.
        """
        if self._bridge_exists():
            logger.info(f"Bridge {self.bridge_name} already exists")
            self._bridge_created = False
            return

        logger.info(f"Creating virtual bridge {self.bridge_name}")

        try:
            # Create bridge
            self._run_cmd(["ip", "link", "add", self.bridge_name, "type", "bridge"])

            # Assign IP address (gateway for VMs)
            self._run_cmd(["ip", "addr", "add", f"{self.gateway}/24", "dev", self.bridge_name])

            # Bring bridge up
            self._run_cmd(["ip", "link", "set", self.bridge_name, "up"])

            # Enable IP forwarding
            self._run_cmd(["sysctl", "-w", "net.ipv4.ip_forward=1"])

            # Set up NAT for outbound traffic
            self._run_cmd([
                "iptables",
                "-t",
                "nat",
                "-A",
                "POSTROUTING",
                "-s",
                self.subnet,
                "-j",
                "MASQUERADE",
            ])

            self._bridge_created = True
            logger.info(f"Bridge {self.bridge_name} created successfully")

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create bridge: {e}")
            self.teardown_bridge()
            raise

    def teardown_bridge(self) -> None:
        """Remove the virtual bridge and clean up networking.

        Only tears down the bridge if it was created by this instance.
        """
        # Remove NAT rule
        try:
            self._run_cmd(
                [
                    "iptables",
                    "-t",
                    "nat",
                    "-D",
                    "POSTROUTING",
                    "-s",
                    self.subnet,
                    "-j",
                    "MASQUERADE",
                ],
                check=False,
            )
        except Exception:
            pass

        # Remove all tap devices
        for tap_name in list(self.tap_devices.keys()):
            self.remove_tap_device(tap_name)

        # Only remove bridge if we created it
        if self._bridge_created and self._bridge_exists():
            try:
                self._run_cmd(["ip", "link", "set", self.bridge_name, "down"])
                self._run_cmd(["ip", "link", "del", self.bridge_name])
                logger.info(f"Bridge {self.bridge_name} removed")
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to remove bridge: {e}")

        self._bridge_created = False

    def _bridge_exists(self) -> bool:
        """Check if the bridge interface exists."""
        try:
            self._run_cmd(["ip", "link", "show", self.bridge_name], capture_output=True)
            return True
        except subprocess.CalledProcessError:
            return False

    def add_tap_device(self, vm_name: str) -> str:
        """Create a tap device for a VM and attach it to the bridge.

        Args:
            vm_name: Name of the VM (used for tap device naming).

        Returns:
            Name of the created tap device.
        """
        # Create deterministic tap name from VM name
        tap_name = f"tap-{vm_name[:8]}"

        if tap_name in self.tap_devices:
            logger.debug(f"Tap device {tap_name} already exists")
            return tap_name

        logger.debug(f"Creating tap device {tap_name} for VM {vm_name}")

        try:
            # Create tap device
            self._run_cmd(["ip", "tuntap", "add", tap_name, "mode", "tap"])

            # Attach to bridge
            self._run_cmd(["ip", "link", "set", tap_name, "master", self.bridge_name])

            # Bring tap up
            self._run_cmd(["ip", "link", "set", tap_name, "up"])

            self.tap_devices[tap_name] = vm_name
            logger.debug(f"Tap device {tap_name} created and attached to bridge")
            return tap_name

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create tap device: {e}")
            raise

    def remove_tap_device(self, tap_name: str) -> None:
        """Remove a tap device.

        Args:
            tap_name: Name of the tap device to remove.
        """
        if tap_name not in self.tap_devices:
            return

        try:
            self._run_cmd(["ip", "link", "del", tap_name], check=False)
            del self.tap_devices[tap_name]
            logger.debug(f"Removed tap device {tap_name}")
        except Exception as e:
            logger.warning(f"Failed to remove tap device {tap_name}: {e}")

    def _run_cmd(
        self,
        cmd: list[str],
        check: bool = True,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess:
        """Run a command, optionally with sudo.

        Args:
            cmd: Command to run.
            check: Raise on non-zero exit.
            capture_output: Capture stdout/stderr.

        Returns:
            CompletedProcess result.
        """
        # Check if we need sudo
        if not self._is_root():
            cmd = ["sudo"] + cmd

        return subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=True,
        )

    def _is_root(self) -> bool:
        """Check if running as root."""
        import os

        return os.geteuid() == 0

    def get_vm_ip(self, role: str) -> str:
        """Get the IP address for a VM role.

        Args:
            role: VM role (source, backup, target).

        Returns:
            IP address for the role.
        """
        ips = {
            "source": "10.100.0.10",
            "backup": "10.100.0.20",
            "target": "10.100.0.30",
        }
        return ips.get(role, "10.100.0.100")

    def get_gateway(self) -> str:
        """Get the gateway IP address."""
        return self.gateway

    def get_nameserver(self) -> str:
        """Get the DNS nameserver to use.

        Returns host's first nameserver from resolv.conf.
        """
        try:
            with open("/etc/resolv.conf") as f:
                for line in f:
                    if line.startswith("nameserver"):
                        return line.split()[1]
        except Exception:
            pass
        # Fallback to common DNS
        return "8.8.8.8"

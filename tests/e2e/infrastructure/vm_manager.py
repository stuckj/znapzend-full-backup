"""
QEMU VM lifecycle management for E2E tests.

Provides functionality to create, start, stop, and manage QEMU virtual machines
for testing the znapzend-full backup/restore workflow.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class VMRole(Enum):
    """Role of a VM in the E2E test."""

    SOURCE = "source"
    BACKUP = "backup"
    TARGET = "target"


@dataclass
class VM:
    """Represents a QEMU virtual machine."""

    name: str
    role: VMRole
    ip_address: str
    mac_address: str
    memory_mb: int = 2048
    cpus: int = 2
    disk_size_gb: int = 10
    disk_path: Path | None = None
    cloud_init_iso: Path | None = None
    pid_file: Path | None = None
    monitor_socket: Path | None = None
    console_log: Path | None = None
    tap_device: str | None = None
    pid: int | None = None

    def is_running(self) -> bool:
        """Check if the VM process is running."""
        if self.pid is None:
            return False
        try:
            os.kill(self.pid, 0)
            return True
        except OSError:
            return False


@dataclass
class QEMUVMManager:
    """Manages QEMU VM lifecycle for E2E tests."""

    base_image: Path
    work_dir: Path
    bridge_name: str = "znapzend-e2e-br0"
    vms: dict[str, VM] = field(default_factory=dict)

    # Static IP assignments for each role
    VM_IPS: dict[VMRole, str] = field(
        default_factory=lambda: {
            VMRole.SOURCE: "10.100.0.10",
            VMRole.BACKUP: "10.100.0.20",
            VMRole.TARGET: "10.100.0.30",
        }
    )

    def __post_init__(self) -> None:
        """Initialize work directory."""
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def _generate_mac(self, role: VMRole) -> str:
        """Generate a deterministic MAC address for a VM role."""
        # Use locally administered MAC address range
        role_byte = {VMRole.SOURCE: "10", VMRole.BACKUP: "20", VMRole.TARGET: "30"}
        return f"52:54:00:e2:e2:{role_byte[role]}"

    def create_vm(
        self,
        name: str,
        role: VMRole,
        memory_mb: int = 2048,
        cpus: int = 2,
        disk_size_gb: int = 10,
    ) -> VM:
        """Create a new VM configuration.

        Args:
            name: VM name.
            role: VM role (source, backup, target).
            memory_mb: RAM in megabytes.
            cpus: Number of virtual CPUs.
            disk_size_gb: Disk size in gigabytes.

        Returns:
            Configured VM object.
        """
        vm_dir = self.work_dir / name
        vm_dir.mkdir(parents=True, exist_ok=True)

        # Create overlay disk on base image
        disk_path = vm_dir / "disk.qcow2"
        self._create_overlay_disk(disk_path, disk_size_gb)

        vm = VM(
            name=name,
            role=role,
            ip_address=self.VM_IPS[role],
            mac_address=self._generate_mac(role),
            memory_mb=memory_mb,
            cpus=cpus,
            disk_size_gb=disk_size_gb,
            disk_path=disk_path,
            pid_file=vm_dir / "qemu.pid",
            monitor_socket=vm_dir / "monitor.sock",
            console_log=vm_dir / "console.log",
        )

        self.vms[name] = vm
        logger.info(f"Created VM {name} with role {role.value} at IP {vm.ip_address}")
        return vm

    def _create_overlay_disk(self, disk_path: Path, size_gb: int) -> None:
        """Create a qcow2 overlay disk backed by the base image."""
        cmd = [
            "qemu-img",
            "create",
            "-f",
            "qcow2",
            "-F",
            "qcow2",
            "-b",
            str(self.base_image.absolute()),
            str(disk_path),
            f"{size_gb}G",
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        logger.debug(f"Created overlay disk: {disk_path}")

    def set_cloud_init_iso(self, vm: VM, iso_path: Path) -> None:
        """Set the cloud-init ISO for a VM."""
        vm.cloud_init_iso = iso_path

    def set_tap_device(self, vm: VM, tap_device: str) -> None:
        """Set the tap device for a VM's network interface."""
        vm.tap_device = tap_device

    def start_vm(self, vm: VM) -> None:
        """Start a VM using QEMU.

        Args:
            vm: VM to start.

        Raises:
            RuntimeError: If VM fails to start.
        """
        if vm.cloud_init_iso is None:
            raise RuntimeError(f"VM {vm.name} has no cloud-init ISO configured")

        if vm.tap_device is None:
            raise RuntimeError(f"VM {vm.name} has no tap device configured")

        cmd = self._build_qemu_command(vm)
        logger.info(f"Starting VM {vm.name}: {' '.join(cmd)}")

        # Open console log file
        console_log = open(vm.console_log, "w")

        # Start QEMU process
        proc = subprocess.Popen(
            cmd,
            stdout=console_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        # Wait briefly for QEMU to start
        time.sleep(2)

        # Check if process is still running
        if proc.poll() is not None:
            console_log.close()
            with open(vm.console_log) as f:
                log_content = f.read()
            raise RuntimeError(f"QEMU failed to start for {vm.name}: {log_content}")

        vm.pid = proc.pid
        logger.info(f"VM {vm.name} started with PID {vm.pid}")

    def _build_qemu_command(self, vm: VM) -> list[str]:
        """Build QEMU command line for launching a VM."""
        cmd = [
            "qemu-system-x86_64",
            # CPU with KVM acceleration
            "-cpu",
            "host",
            "-enable-kvm",
            # Memory and CPUs
            "-m",
            f"{vm.memory_mb}M",
            "-smp",
            str(vm.cpus),
            # Machine type
            "-machine",
            "q35,accel=kvm",
            # Headless operation
            "-display",
            "none",
            "-serial",
            "stdio",
            # Main disk (overlay on base)
            "-drive",
            f"file={vm.disk_path},format=qcow2,if=virtio",
            # Cloud-init ISO
            "-drive",
            f"file={vm.cloud_init_iso},format=raw,if=virtio,readonly=on",
            # Networking via tap device on bridge
            "-netdev",
            f"tap,id=net0,ifname={vm.tap_device},script=no,downscript=no",
            "-device",
            f"virtio-net-pci,netdev=net0,mac={vm.mac_address}",
            # Random number generator
            "-object",
            "rng-random,id=rng0,filename=/dev/urandom",
            "-device",
            "virtio-rng-pci,rng=rng0",
            # QEMU monitor socket for management
            "-monitor",
            f"unix:{vm.monitor_socket},server,nowait",
        ]
        return cmd

    def stop_vm(self, vm: VM, force: bool = False, timeout: int = 30) -> None:
        """Stop a running VM.

        Args:
            vm: VM to stop.
            force: If True, kill immediately. Otherwise, try graceful shutdown.
            timeout: Seconds to wait for graceful shutdown before forcing.
        """
        if not vm.is_running():
            logger.debug(f"VM {vm.name} is not running")
            return

        if force:
            self._kill_vm(vm)
            return

        # Try graceful shutdown via QEMU monitor
        try:
            self._send_monitor_command(vm, "system_powerdown")
            deadline = time.time() + timeout
            while time.time() < deadline:
                if not vm.is_running():
                    logger.info(f"VM {vm.name} shut down gracefully")
                    return
                time.sleep(1)
            logger.warning(f"VM {vm.name} did not shut down gracefully, forcing")
        except Exception as e:
            logger.warning(f"Graceful shutdown failed for {vm.name}: {e}")

        self._kill_vm(vm)

    def _kill_vm(self, vm: VM) -> None:
        """Forcefully kill a VM process."""
        if vm.pid is None:
            return

        try:
            os.kill(vm.pid, signal.SIGKILL)
            # Wait for process to die
            for _ in range(10):
                try:
                    os.kill(vm.pid, 0)
                    time.sleep(0.1)
                except OSError:
                    break
            logger.info(f"VM {vm.name} killed")
        except OSError as e:
            logger.debug(f"Error killing VM {vm.name}: {e}")
        finally:
            vm.pid = None

    def _send_monitor_command(self, vm: VM, command: str) -> str:
        """Send a command to QEMU monitor socket."""
        import socket

        if not vm.monitor_socket or not vm.monitor_socket.exists():
            raise RuntimeError(f"Monitor socket not available for {vm.name}")

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5)
        try:
            sock.connect(str(vm.monitor_socket))
            # Read initial prompt
            sock.recv(4096)
            # Send command
            sock.sendall(f"{command}\n".encode())
            time.sleep(0.5)
            response = sock.recv(4096).decode()
            return response
        finally:
            sock.close()

    def wait_for_ready(self, vm: VM, timeout: int = 300) -> bool:
        """Wait for a VM to be ready (SSH accessible).

        Args:
            vm: VM to wait for.
            timeout: Maximum seconds to wait.

        Returns:
            True if VM is ready, False if timeout.
        """
        from ..utils.wait_helpers import wait_for_ssh

        logger.info(f"Waiting for VM {vm.name} to be ready...")
        return wait_for_ssh(vm.ip_address, timeout=timeout)

    def cleanup_vm(self, vm: VM) -> None:
        """Clean up a single VM's resources."""
        self.stop_vm(vm, force=True)

        # Remove disk overlay
        if vm.disk_path and vm.disk_path.exists():
            vm.disk_path.unlink()

        # Remove cloud-init ISO
        if vm.cloud_init_iso and vm.cloud_init_iso.exists():
            vm.cloud_init_iso.unlink()

        # Remove PID file
        if vm.pid_file and vm.pid_file.exists():
            vm.pid_file.unlink()

        # Remove monitor socket
        if vm.monitor_socket and vm.monitor_socket.exists():
            vm.monitor_socket.unlink()

        logger.info(f"Cleaned up VM {vm.name}")

    def cleanup_all(self) -> None:
        """Clean up all VMs and resources."""
        for vm in list(self.vms.values()):
            self.cleanup_vm(vm)
        self.vms.clear()
        logger.info("All VMs cleaned up")

    def get_vm(self, name: str) -> VM | None:
        """Get a VM by name."""
        return self.vms.get(name)

"""
E2E test fixtures for QEMU-based testing.

Provides pytest fixtures for setting up and tearing down the VM-based
test environment for end-to-end backup/restore testing.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Generator

import pytest

from .infrastructure.cloud_init import CloudInitGenerator
from .infrastructure.image_builder import ImageBuilder
from .infrastructure.network_manager import VirtualNetworkManager
from .infrastructure.ssh_manager import SSHManager
from .infrastructure.vm_manager import QEMUVMManager, VM, VMRole
from .utils.wait_helpers import wait_for_ssh, wait_for_cloud_init

if TYPE_CHECKING:
    import paramiko

logger = logging.getLogger(__name__)


# Environment variable overrides
E2E_WORK_DIR = os.environ.get("E2E_WORK_DIR", "/tmp/znapzend-e2e")
E2E_IMAGE_CACHE = os.environ.get("E2E_IMAGE_CACHE", str(Path.home() / ".cache" / "znapzend-full-e2e"))


@pytest.fixture(scope="session")
def e2e_work_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a session-wide work directory for E2E tests.

    Returns:
        Path to the work directory.
    """
    if E2E_WORK_DIR:
        work_dir = Path(E2E_WORK_DIR)
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir
    return tmp_path_factory.mktemp("e2e_work")


@pytest.fixture(scope="session")
def image_cache_dir() -> Path:
    """Get the image cache directory.

    Returns:
        Path to the image cache directory.
    """
    cache_dir = Path(E2E_IMAGE_CACHE)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


@pytest.fixture(scope="session")
def image_builder(image_cache_dir: Path) -> ImageBuilder:
    """Create an image builder instance.

    Args:
        image_cache_dir: Cache directory for images.

    Returns:
        ImageBuilder instance.
    """
    return ImageBuilder(cache_dir=image_cache_dir)


@pytest.fixture(scope="session")
def base_image(image_builder: ImageBuilder) -> Path:
    """Build or get cached base test image.

    This fixture builds the base Ubuntu image with ZFS support
    if it doesn't exist, or returns the cached version.

    Args:
        image_builder: ImageBuilder instance.

    Returns:
        Path to the base test image.
    """
    logger.info("Preparing base test image...")
    return image_builder.build_test_image()


@pytest.fixture(scope="session")
def network_manager() -> Generator[VirtualNetworkManager, None, None]:
    """Set up virtual network for VM communication.

    Creates a Linux bridge with NAT for VM networking.
    Requires root privileges.

    Yields:
        VirtualNetworkManager instance with active bridge.
    """
    logger.info("Setting up virtual network...")
    mgr = VirtualNetworkManager()
    mgr.setup_bridge()
    yield mgr
    logger.info("Tearing down virtual network...")
    mgr.teardown_bridge()


@pytest.fixture(scope="session")
def ssh_manager(e2e_work_dir: Path) -> SSHManager:
    """Create SSH manager with generated keypair.

    Args:
        e2e_work_dir: Work directory for SSH keys.

    Returns:
        SSHManager instance with generated keypair.
    """
    logger.info("Setting up SSH manager...")
    mgr = SSHManager(work_dir=e2e_work_dir / "ssh")
    mgr.generate_keypair()
    return mgr


@pytest.fixture(scope="function")
def vm_manager(
    base_image: Path,
    e2e_work_dir: Path,
    network_manager: VirtualNetworkManager,
) -> Generator[QEMUVMManager, None, None]:
    """Create VM manager for a single test.

    Each test gets a fresh VM manager that cleans up all VMs
    when the test completes.

    Args:
        base_image: Path to base test image.
        e2e_work_dir: Work directory.
        network_manager: Network manager.

    Yields:
        QEMUVMManager instance.
    """
    import uuid
    test_id = str(uuid.uuid4())[:8]
    vm_work_dir = e2e_work_dir / "vms" / test_id

    mgr = QEMUVMManager(
        base_image=base_image,
        work_dir=vm_work_dir,
        bridge_name=network_manager.bridge_name,
    )

    yield mgr

    # Cleanup all VMs
    mgr.cleanup_all()


@pytest.fixture(scope="function")
def cloud_init_generator(
    e2e_work_dir: Path,
    ssh_manager: SSHManager,
    network_manager: VirtualNetworkManager,
) -> CloudInitGenerator:
    """Create cloud-init generator.

    Args:
        e2e_work_dir: Work directory.
        ssh_manager: SSH manager with keypair.
        network_manager: Network manager.

    Returns:
        CloudInitGenerator instance.
    """
    import uuid
    test_id = str(uuid.uuid4())[:8]

    return CloudInitGenerator(
        work_dir=e2e_work_dir / "cloud-init" / test_id,
        ssh_public_key=ssh_manager.get_public_key(),
        gateway=network_manager.get_gateway(),
        nameserver=network_manager.get_nameserver(),
    )


def _create_and_start_vm(
    vm_manager: QEMUVMManager,
    network_manager: VirtualNetworkManager,
    cloud_init_generator: CloudInitGenerator,
    ssh_manager: SSHManager,
    name: str,
    role: VMRole,
    memory_mb: int = 2048,
    cpus: int = 2,
    disk_size_gb: int = 10,
) -> tuple[VM, "paramiko.SSHClient"]:
    """Helper to create, configure, and start a VM.

    Args:
        vm_manager: VM manager.
        network_manager: Network manager.
        cloud_init_generator: Cloud-init generator.
        ssh_manager: SSH manager.
        name: VM name.
        role: VM role.
        memory_mb: RAM in MB.
        cpus: Number of CPUs.
        disk_size_gb: Disk size in GB.

    Returns:
        Tuple of (VM, SSH client).
    """
    # Create VM
    vm = vm_manager.create_vm(
        name=name,
        role=role,
        memory_mb=memory_mb,
        cpus=cpus,
        disk_size_gb=disk_size_gb,
    )

    # Create tap device
    tap_device = network_manager.add_tap_device(name)
    vm_manager.set_tap_device(vm, tap_device)

    # Generate cloud-init ISO
    cloud_init_iso = cloud_init_generator.generate_iso(
        vm_name=name,
        role=role.value,
        ip_address=vm.ip_address,
    )
    vm_manager.set_cloud_init_iso(vm, cloud_init_iso)

    # Start VM
    vm_manager.start_vm(vm)

    # Wait for VM to be ready
    logger.info(f"Waiting for {name} to be ready...")
    if not wait_for_ssh(vm.ip_address, timeout=120):
        raise RuntimeError(f"Timeout waiting for SSH on {name}")

    # Connect via SSH
    ssh_client = ssh_manager.connect(vm.ip_address)

    # Wait for cloud-init
    if not wait_for_cloud_init(ssh_client, timeout=300):
        raise RuntimeError(f"Timeout waiting for cloud-init on {name}")

    # Copy SSH key for inter-VM communication
    ssh_manager.copy_private_key_to_vm(ssh_client)

    logger.info(f"VM {name} is ready")
    return vm, ssh_client


@pytest.fixture
def source_vm(
    vm_manager: QEMUVMManager,
    network_manager: VirtualNetworkManager,
    cloud_init_generator: CloudInitGenerator,
    ssh_manager: SSHManager,
) -> Generator[tuple[VM, "paramiko.SSHClient"], None, None]:
    """Create and start source VM.

    The source VM has:
    - testpool ZFS pool
    - testpool/ROOT and testpool/data datasets
    - testpool/znapzend-full-meta metadata dataset

    Yields:
        Tuple of (VM, SSH client).
    """
    vm, ssh_client = _create_and_start_vm(
        vm_manager=vm_manager,
        network_manager=network_manager,
        cloud_init_generator=cloud_init_generator,
        ssh_manager=ssh_manager,
        name="source",
        role=VMRole.SOURCE,
        memory_mb=2048,
        cpus=2,
        disk_size_gb=10,
    )

    yield vm, ssh_client

    ssh_manager.close(ssh_client)


@pytest.fixture
def backup_vm(
    vm_manager: QEMUVMManager,
    network_manager: VirtualNetworkManager,
    cloud_init_generator: CloudInitGenerator,
    ssh_manager: SSHManager,
) -> Generator[tuple[VM, "paramiko.SSHClient"], None, None]:
    """Create and start backup VM.

    The backup VM has:
    - backuppool ZFS pool
    - backuppool/backups dataset for receiving backups

    Yields:
        Tuple of (VM, SSH client).
    """
    vm, ssh_client = _create_and_start_vm(
        vm_manager=vm_manager,
        network_manager=network_manager,
        cloud_init_generator=cloud_init_generator,
        ssh_manager=ssh_manager,
        name="backup",
        role=VMRole.BACKUP,
        memory_mb=2048,
        cpus=2,
        disk_size_gb=20,
    )

    yield vm, ssh_client

    ssh_manager.close(ssh_client)


@pytest.fixture
def target_vm(
    vm_manager: QEMUVMManager,
    network_manager: VirtualNetworkManager,
    cloud_init_generator: CloudInitGenerator,
    ssh_manager: SSHManager,
) -> Generator[tuple[VM, "paramiko.SSHClient"], None, None]:
    """Create and start target VM.

    The target VM has:
    - restorepool ZFS pool (empty, for receiving restored data)

    Yields:
        Tuple of (VM, SSH client).
    """
    vm, ssh_client = _create_and_start_vm(
        vm_manager=vm_manager,
        network_manager=network_manager,
        cloud_init_generator=cloud_init_generator,
        ssh_manager=ssh_manager,
        name="target",
        role=VMRole.TARGET,
        memory_mb=2048,
        cpus=2,
        disk_size_gb=10,
    )

    yield vm, ssh_client

    ssh_manager.close(ssh_client)


@pytest.fixture
def three_vm_environment(
    source_vm: tuple[VM, "paramiko.SSHClient"],
    backup_vm: tuple[VM, "paramiko.SSHClient"],
    target_vm: tuple[VM, "paramiko.SSHClient"],
) -> dict[str, tuple[VM, "paramiko.SSHClient"]]:
    """Create a full 3-VM test environment.

    This fixture ensures all three VMs are created and ready.

    Returns:
        Dict with 'source', 'backup', and 'target' keys.
    """
    return {
        "source": source_vm,
        "backup": backup_vm,
        "target": target_vm,
    }

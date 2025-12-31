# E2E Testing Framework

This document describes the end-to-end (E2E) test framework for znapzend-full. The framework uses QEMU virtual machines to test complete backup/restore cycles in an isolated environment.

## Overview

The E2E test framework validates the complete backup and restore lifecycle using three QEMU virtual machines:

```
┌─────────────┐     zfs send/recv    ┌─────────────┐
│  Source VM  │ ──────────────────── │  Backup VM  │
│  10.100.0.10│      via SSH         │  10.100.0.20│
│  - testpool │                      │  - backuppool│
└─────────────┘                      └─────────────┘
                                            │
                                            │ zfs send/recv
                                            ▼
                                     ┌─────────────┐
                                     │  Target VM  │
                                     │  10.100.0.30│
                                     │  - restorepool│
                                     └─────────────┘

All VMs connected via virtual bridge: znapzend-e2e-br0 (10.100.0.0/24)
```

### VM Roles

| VM | IP Address | ZFS Pool | Purpose |
|----|------------|----------|---------|
| Source | 10.100.0.10 | testpool | Original system with data to backup |
| Backup | 10.100.0.20 | backuppool | Receives and stores backups |
| Target | 10.100.0.30 | restorepool | Receives restored data for verification |

## Prerequisites

### Hardware Requirements

- **CPU**: x86_64 with hardware virtualization (VT-x/AMD-V)
- **RAM**: 8GB minimum (each VM uses 2GB)
- **Disk**: 50GB free space (base image + VM overlays)

### Software Requirements

```bash
# Ubuntu/Debian
sudo apt-get install \
    qemu-system-x86 \
    qemu-utils \
    libguestfs-tools \
    cloud-image-utils \
    genisoimage \
    bridge-utils \
    iproute2

# Python dependencies
pip install paramiko jinja2 pytest-timeout pyyaml
```

### KVM Access

Ensure your user has access to KVM:

```bash
# Check KVM availability
ls -la /dev/kvm

# Add user to kvm group if needed
sudo usermod -aG kvm $USER
# (logout and login again)
```

## Directory Structure

```
tests/e2e/
├── __init__.py
├── conftest.py                    # Pytest fixtures
├── test_full_backup_restore.py    # Main E2E tests
├── infrastructure/
│   ├── __init__.py
│   ├── vm_manager.py              # QEMU VM lifecycle
│   ├── network_manager.py         # Virtual bridge management
│   ├── ssh_manager.py             # SSH key + connections
│   ├── image_builder.py           # Base image creation
│   └── cloud_init.py              # Cloud-init generation (generates configs dynamically)
├── utils/
│   ├── __init__.py
│   ├── wait_helpers.py            # VM readiness checks
│   └── checksum_helpers.py        # Data verification
└── images/
    ├── build_base_image.sh        # Image build script
    └── Makefile                   # Build automation
```

**Note:** Cloud-init configurations are generated dynamically by `cloud_init.py` based on VM role, not from static template files.

## Running E2E Tests

**Note:** E2E tests require root/sudo privileges to create virtual network bridges and tap devices.

### Building the Base Image

First-time setup requires building the base VM image:

```bash
cd tests/e2e/images
sudo make image
```

This downloads Ubuntu 24.04 cloud image and optionally pre-installs ZFS support (falls back to cloud-init installation if virt-customize fails). The image is cached at `~/.cache/znapzend-full-e2e/`.

To rebuild the image:

```bash
sudo make clean
sudo make image
```

### Running Tests Locally

Tests require root for network setup:

```bash
# Run all E2E tests (requires sudo for network bridge creation)
sudo pytest tests/e2e/ -v --timeout=1200

# Run specific test
sudo pytest tests/e2e/test_full_backup_restore.py::TestFullBackupRestore::test_backup_and_restore_cycle -v

# Run with debug logging
sudo pytest tests/e2e/ -v --log-cli-level=DEBUG

# Override work directory
sudo E2E_WORK_DIR=/tmp/my-e2e-test pytest tests/e2e/ -v
```

**Tip:** If running as root, ensure Python dependencies are installed:
```bash
sudo pip install paramiko jinja2 pytest-timeout pyyaml --break-system-packages
# OR use a virtual environment:
sudo python3 -m venv /opt/e2e-venv
sudo /opt/e2e-venv/bin/pip install paramiko jinja2 pytest-timeout pyyaml
sudo /opt/e2e-venv/bin/pytest tests/e2e/ -v --timeout=1200
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `E2E_WORK_DIR` | `/tmp/znapzend-e2e` | Working directory for VMs |
| `E2E_IMAGE_CACHE` | `~/.cache/znapzend-full-e2e` | Image cache directory |

## Test Architecture

### Infrastructure Layer

#### QEMUVMManager (`infrastructure/vm_manager.py`)

Manages QEMU virtual machine lifecycle:

```python
# Create VM
vm = vm_manager.create_vm(
    name="source",
    role=VMRole.SOURCE,
    memory_mb=2048,
    cpus=2,
    disk_size_gb=10,
)

# Start VM
vm_manager.start_vm(vm)

# Stop VM
vm_manager.stop_vm(vm)

# Cleanup all VMs
vm_manager.cleanup_all()
```

Features:
- Overlay disks (qcow2) on cached base image
- KVM acceleration when available
- Tap networking for VM-to-VM communication
- Console logging for debugging

#### VirtualNetworkManager (`infrastructure/network_manager.py`)

Creates virtual networking infrastructure:

```python
network_manager = VirtualNetworkManager()
network_manager.setup_bridge()

# Add tap device for VM
tap_device = network_manager.add_tap_device("source")

# Cleanup
network_manager.teardown_bridge()
```

Features:
- Linux bridge creation (`znapzend-e2e-br0`)
- Automatic IP assignment based on VM role
- NAT for internet access
- Tap device management

#### SSHManager (`infrastructure/ssh_manager.py`)

Handles SSH connections to VMs:

```python
ssh_manager = SSHManager(work_dir=Path("/tmp/ssh"))
ssh_manager.generate_keypair()

# Connect to VM
ssh_client = ssh_manager.connect("10.100.0.10")

# Execute command
exit_code, stdout, stderr = ssh_manager.execute(ssh_client, "zfs list")

# Close connection
ssh_manager.close(ssh_client)
```

Features:
- Ephemeral SSH keypair per test run
- Key injection via cloud-init
- Inter-VM SSH key distribution

### Cloud-Init Provisioning

VMs are provisioned via cloud-init with role-specific configuration:

#### Source VM
- Creates `testpool` with data and ROOT datasets
- Creates `testpool/znapzend-full-meta` for metadata
- Configures SSH access

#### Backup VM
- Creates `backuppool` for receiving snapshots
- Configures SSH access

#### Target VM
- Creates empty `restorepool`
- Configures SSH access

### Test Utilities

#### Wait Helpers (`utils/wait_helpers.py`)

```python
# Wait for SSH availability
wait_for_ssh("10.100.0.10", timeout=120)

# Wait for ZFS pool
wait_for_zpool(ssh_client, "testpool", timeout=60)

# Wait for cloud-init completion
wait_for_cloud_init(ssh_client, timeout=300)
```

#### Checksum Helpers (`utils/checksum_helpers.py`)

```python
# Compute checksums
source_checksums = compute_remote_checksum(ssh_client, "/testpool/data")

# Compare checksums
match, differences = compare_checksums(source_checksums, target_checksums)

# Verify ZFS properties
match, errors = verify_zfs_properties(ssh_client, "testpool/data", expected_props)
```

## Pytest Fixtures

### Session-Scoped Fixtures

These are created once per test session:

```python
@pytest.fixture(scope="session")
def base_image(image_builder)
    # Build or return cached base image

@pytest.fixture(scope="session")
def network_manager()
    # Set up virtual bridge (requires root)

@pytest.fixture(scope="session")
def ssh_manager(e2e_work_dir)
    # Generate SSH keypair
```

### Function-Scoped Fixtures

These are created fresh for each test:

```python
@pytest.fixture
def source_vm(vm_manager, network_manager, ...)
    # Create and start source VM

@pytest.fixture
def backup_vm(vm_manager, network_manager, ...)
    # Create and start backup VM

@pytest.fixture
def target_vm(vm_manager, network_manager, ...)
    # Create and start target VM

@pytest.fixture
def three_vm_environment(source_vm, backup_vm, target_vm)
    # All three VMs ready
```

## Writing New E2E Tests

### Basic Test Structure

```python
import pytest
from .infrastructure.vm_manager import VM
from .utils.wait_helpers import wait_for_zpool

class TestMyFeature:
    @pytest.mark.timeout(900)  # 15 minute timeout
    def test_my_scenario(
        self,
        three_vm_environment: dict[str, tuple[VM, "paramiko.SSHClient"]],
        ssh_manager,
    ):
        source_vm, source_ssh = three_vm_environment["source"]
        backup_vm, backup_ssh = three_vm_environment["backup"]

        # Wait for pools
        assert wait_for_zpool(source_ssh, "testpool", timeout=60)

        # Execute commands
        exit_code, stdout, stderr = ssh_manager.execute(
            source_ssh, "zfs list"
        )
        assert exit_code == 0

        # Verify results
        assert "testpool" in stdout
```

### Using Single VM

For tests that only need one VM:

```python
def test_source_only(
    self,
    source_vm: tuple[VM, "paramiko.SSHClient"],
    ssh_manager,
):
    vm, ssh = source_vm
    # ... test code
```

### Test Data Creation

```python
@pytest.fixture
def test_data(
    self,
    source_vm: tuple[VM, "paramiko.SSHClient"],
    ssh_manager,
) -> dict[str, str]:
    vm, ssh = source_vm

    # Create test files
    ssh_manager.execute(ssh, "echo 'test' > /testpool/data/test.txt")

    # Compute checksums
    from .utils.checksum_helpers import compute_remote_checksum
    return compute_remote_checksum(ssh, "/testpool/data")
```

## CI Integration

### GitHub Actions Workflow

The E2E tests run automatically on:
- Push to main branch
- Pull requests to main
- Manual workflow dispatch

The workflow:
1. Checks for nested virtualization support
2. Installs QEMU and dependencies
3. Caches the base VM image
4. Sets up virtual networking
5. Runs pytest with extended timeout
6. Collects logs on failure
7. Cleans up networking

### Running in CI

```yaml
# .github/workflows/e2e-tests.yml
- name: Run E2E tests
  run: |
    pytest tests/e2e/ \
      -v \
      --tb=long \
      --timeout=1200 \
      -x \
      --log-cli-level=INFO
```

### Debugging CI Failures

Enable tmate debugging:

```yaml
# Trigger workflow manually with debug_enabled=true
workflow_dispatch:
  inputs:
    debug_enabled:
      default: 'false'
```

Or examine uploaded artifacts:
- `e2e-pytest.log`: Full pytest output
- `console.log`: VM console output
- `user-data`: Cloud-init configuration

## Troubleshooting

### VM Won't Start

```bash
# Check KVM access
ls -la /dev/kvm

# Check if QEMU is installed
which qemu-system-x86_64

# Check for existing VMs
ps aux | grep qemu
```

### SSH Connection Fails

```bash
# Check bridge exists
ip addr show znapzend-e2e-br0

# Check VM is running
ps aux | grep qemu

# Test connectivity
ping 10.100.0.10
```

### Cloud-Init Timeout

Check cloud-init logs:

```bash
# From VM console (via QEMU monitor) or SSH
cat /var/log/cloud-init-output.log
cat /var/log/cloud-init.log
```

### ZFS Pool Not Ready

```bash
# Check ZFS module
lsmod | grep zfs

# Check pool status
zpool status testpool

# Check for ZFS errors
dmesg | grep -i zfs
```

### Network Issues Between VMs

```bash
# From source VM
ping 10.100.0.20  # backup VM
ssh root@10.100.0.20  # should work with key

# Check iptables NAT
sudo iptables -t nat -L -n
```

## Technical Details

### ZFS in VMs

VMs use file-backed ZFS pools created in `/tmp`:

```bash
# Pool creation in cloud-init (source VM example)
truncate -s 2G /tmp/zfs-disk.img
zpool create -f testpool /tmp/zfs-disk.img
```

ARC is tuned to 256MB to prevent memory pressure in VMs:

```bash
# Set via /etc/modprobe.d/zfs.conf
options zfs zfs_arc_max=268435456
```

### VM Readiness Detection

VMs are considered ready when:
1. SSH port (22) accepts connections
2. Cloud-init reports "done" status
3. `/var/run/e2e-ready` marker file exists
4. ZFS pool is ONLINE

### Image Caching

Base images are cached to avoid repeated downloads:

```
~/.cache/znapzend-full-e2e/
├── ubuntu-noble-base.qcow2      # Downloaded Ubuntu 24.04 cloud image
└── znapzend-full-test.qcow2     # Resized/customized test image
```

## Resource Usage

| Resource | Per VM | Total (3 VMs) |
|----------|--------|---------------|
| RAM | 2GB | 6GB |
| CPUs | 2 | 6 |
| Disk (base) | - | ~600MB (shared) |
| Disk (overlay) | ~1GB | ~3GB |
| Test runtime | - | 15-30 minutes |

**Note:** First run takes longer as cloud-init installs packages. Subsequent runs are faster if using pre-built images with packages.

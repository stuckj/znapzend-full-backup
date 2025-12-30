"""Shared test fixtures for znapzend-full."""

import sys
from pathlib import Path

# Add src directory to path for testing without installation
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import pytest
import tempfile
import yaml


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_config_dict():
    """Sample configuration as dictionary."""
    return {
        "version": 1,
        "metadata_dataset": "testpool/znapzend-full-meta",
        "datasets": [
            {
                "name": "testpool/ROOT",
                "recursive": True,
                "exclude": ["testpool/ROOT/tmp"],
                "destination": "backup-server:tank/backups/test/ROOT",
                "retention": {
                    "hourly": 24,
                    "daily": 7,
                    "weekly": 4,
                    "monthly": 12,
                    "yearly": 0,
                },
                "enabled": True,
            },
            {
                "name": "testpool/home",
                "recursive": True,
                "exclude": [],
                "destination": "backup-server:tank/backups/test/home",
                "retention": {
                    "hourly": 48,
                    "daily": 30,
                    "weekly": 8,
                    "monthly": 24,
                    "yearly": 2,
                },
                "enabled": True,
            },
        ],
        "additional_backups": {
            "efi_partitions": ["/dev/sda1"],
            "gpt_backup": ["/dev/sda"],
            "zpool_properties": ["testpool"],
            "zfs_properties": ["testpool"],
        },
        "destinations": [
            {
                "name": "backup-server",
                "host": "backup.local",
                "user": "root",
                "port": 22,
                "ssh_key": "/root/.ssh/id_backup",
            }
        ],
        "schedule": {
            "quiet_hours": {
                "start": "02:00",
                "end": "06:00",
            }
        },
    }


@pytest.fixture
def sample_config_file(temp_dir, sample_config_dict):
    """Create a sample configuration file."""
    config_path = temp_dir / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(sample_config_dict, f)
    return config_path


@pytest.fixture
def minimal_config_dict():
    """Minimal valid configuration."""
    return {
        "version": 1,
        "metadata_dataset": "rpool/meta",
        "datasets": [],
        "additional_backups": {
            "efi_partitions": [],
            "gpt_backup": [],
            "zpool_properties": [],
            "zfs_properties": [],
        },
        "destinations": [],
        "schedule": {"quiet_hours": {"start": "", "end": ""}},
    }


@pytest.fixture
def hash_tracker_dir(temp_dir):
    """Create a directory structure for hash tracker tests."""
    base = temp_dir / "metadata"
    base.mkdir()
    (base / "efi").mkdir()
    (base / "gpt").mkdir()
    (base / "zpool").mkdir()
    (base / "zfs").mkdir()
    return base


@pytest.fixture
def sample_zfs_properties():
    """Sample ZFS properties output."""
    return """NAME\tPROPERTY\tVALUE\tSOURCE
testpool\ttype\tfilesystem\t-
testpool\tcompression\tlz4\tlocal
testpool\tmountpoint\t/testpool\tlocal
testpool\tatime\toff\tlocal
testpool/ROOT\ttype\tfilesystem\t-
testpool/ROOT\tcompression\tlz4\tinherited from testpool
testpool/ROOT\tmountpoint\t/\tlocal
testpool/home\ttype\tfilesystem\t-
testpool/home\tcompression\tlz4\tinherited from testpool
testpool/home\tmountpoint\t/home\tlocal
"""


@pytest.fixture
def sample_zpool_status():
    """Sample zpool status output."""
    return """  pool: testpool
 state: ONLINE
config:

\tNAME                                     STATE     READ WRITE CKSUM
\ttestpool                                 ONLINE       0     0     0
\t  mirror-0                               ONLINE       0     0     0
\t    /dev/disk/by-id/nvme-device1-part3   ONLINE       0     0     0
\t    /dev/disk/by-id/nvme-device2-part3   ONLINE       0     0     0

errors: No known data errors
"""

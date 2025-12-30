"""Tests for znapzend_full.config module."""

import pytest
from pathlib import Path
import yaml

from znapzend_full.config import (
    Config,
    DatasetConfig,
    DestinationConfig,
    RetentionPolicy,
    AdditionalBackups,
    ScheduleConfig,
    load_config,
    save_config,
    validate_config,
    get_default_config,
    DEFAULT_CONFIG_PATH,
)


class TestRetentionPolicy:
    """Tests for RetentionPolicy dataclass."""

    def test_default_values(self):
        policy = RetentionPolicy()
        assert policy.hourly == 24
        assert policy.daily == 7
        assert policy.weekly == 4
        assert policy.monthly == 12
        assert policy.yearly == 0

    def test_custom_values(self):
        policy = RetentionPolicy(
            hourly=48, daily=14, weekly=8, monthly=24, yearly=5
        )
        assert policy.hourly == 48
        assert policy.daily == 14
        assert policy.weekly == 8
        assert policy.monthly == 24
        assert policy.yearly == 5

    def test_to_znapzend_format_default(self):
        policy = RetentionPolicy()
        result = policy.to_znapzend_format()
        assert "24h=>1h" in result
        assert "7d=>1d" in result
        assert "4w=>1w" in result
        assert "12m=>1m" in result

    def test_to_znapzend_format_with_yearly(self):
        policy = RetentionPolicy(yearly=3)
        result = policy.to_znapzend_format()
        assert "3y=>1y" in result

    def test_to_znapzend_format_zeros_excluded(self):
        policy = RetentionPolicy(hourly=0, daily=7, weekly=0, monthly=0, yearly=0)
        result = policy.to_znapzend_format()
        assert result == "7d=>1d"


class TestDatasetConfig:
    """Tests for DatasetConfig dataclass."""

    def test_default_values(self):
        ds = DatasetConfig(name="rpool/ROOT")
        assert ds.name == "rpool/ROOT"
        assert ds.recursive is True
        assert ds.exclude == []
        assert ds.destination == ""
        assert ds.enabled is True

    def test_with_all_options(self):
        ds = DatasetConfig(
            name="rpool/ROOT",
            recursive=False,
            exclude=["rpool/ROOT/tmp"],
            destination="backup:tank/root",
            retention=RetentionPolicy(hourly=12),
            enabled=False,
        )
        assert ds.recursive is False
        assert ds.exclude == ["rpool/ROOT/tmp"]
        assert ds.destination == "backup:tank/root"
        assert ds.retention.hourly == 12
        assert ds.enabled is False


class TestDestinationConfig:
    """Tests for DestinationConfig dataclass."""

    def test_default_values(self):
        dest = DestinationConfig(name="backup", host="backup.local")
        assert dest.name == "backup"
        assert dest.host == "backup.local"
        assert dest.user == "root"
        assert dest.port == 22
        assert dest.ssh_key == ""

    def test_ssh_uri(self):
        dest = DestinationConfig(
            name="backup",
            host="backup.local",
            user="admin",
            port=2222,
        )
        uri = dest.ssh_uri()
        assert uri == "ssh://admin@backup.local:2222"


class TestConfig:
    """Tests for Config dataclass."""

    def test_default_values(self):
        config = Config()
        assert config.version == 1
        assert config.metadata_dataset == "rpool/znapzend-full-meta"
        assert config.datasets == []
        assert config.destinations == []

    def test_from_dict(self, sample_config_dict):
        config = Config.from_dict(sample_config_dict)
        assert config.version == 1
        assert config.metadata_dataset == "testpool/znapzend-full-meta"
        assert len(config.datasets) == 2
        assert len(config.destinations) == 1

        # Check first dataset
        ds = config.datasets[0]
        assert ds.name == "testpool/ROOT"
        assert ds.recursive is True
        assert ds.exclude == ["testpool/ROOT/tmp"]
        assert ds.retention.hourly == 24

        # Check destination
        dest = config.destinations[0]
        assert dest.name == "backup-server"
        assert dest.host == "backup.local"

        # Check additional backups
        assert config.additional_backups.efi_partitions == ["/dev/sda1"]
        assert config.additional_backups.gpt_backup == ["/dev/sda"]

    def test_from_dict_minimal(self, minimal_config_dict):
        config = Config.from_dict(minimal_config_dict)
        assert config.version == 1
        assert len(config.datasets) == 0
        assert len(config.destinations) == 0

    def test_from_dict_empty(self):
        config = Config.from_dict({})
        assert config.version == 1
        assert config.metadata_dataset == "rpool/znapzend-full-meta"

    def test_to_dict(self, sample_config_dict):
        config = Config.from_dict(sample_config_dict)
        result = config.to_dict()

        assert result["version"] == 1
        assert result["metadata_dataset"] == "testpool/znapzend-full-meta"
        assert len(result["datasets"]) == 2
        assert len(result["destinations"]) == 1

    def test_roundtrip(self, sample_config_dict):
        """Test that from_dict -> to_dict produces equivalent config."""
        config = Config.from_dict(sample_config_dict)
        result = config.to_dict()

        # Reload from result
        config2 = Config.from_dict(result)

        assert config.version == config2.version
        assert config.metadata_dataset == config2.metadata_dataset
        assert len(config.datasets) == len(config2.datasets)
        assert config.datasets[0].name == config2.datasets[0].name


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_valid_config(self, sample_config_file):
        config = load_config(sample_config_file)
        assert config.version == 1
        assert len(config.datasets) == 2

    def test_load_missing_file(self, temp_dir):
        with pytest.raises(FileNotFoundError):
            load_config(temp_dir / "nonexistent.yaml")

    def test_load_invalid_yaml(self, temp_dir):
        bad_file = temp_dir / "bad.yaml"
        bad_file.write_text("{ invalid yaml [")

        with pytest.raises(yaml.YAMLError):
            load_config(bad_file)

    def test_load_empty_file(self, temp_dir):
        empty_file = temp_dir / "empty.yaml"
        empty_file.write_text("")

        config = load_config(empty_file)
        assert config.version == 1  # Uses defaults


class TestSaveConfig:
    """Tests for save_config function."""

    def test_save_config(self, temp_dir, sample_config_dict):
        config = Config.from_dict(sample_config_dict)
        config_path = temp_dir / "output.yaml"

        save_config(config, config_path)

        assert config_path.exists()

        # Reload and verify
        loaded = load_config(config_path)
        assert loaded.version == config.version
        assert len(loaded.datasets) == len(config.datasets)

    def test_save_creates_parent_dirs(self, temp_dir, sample_config_dict):
        config = Config.from_dict(sample_config_dict)
        config_path = temp_dir / "subdir" / "nested" / "config.yaml"

        save_config(config, config_path)

        assert config_path.exists()


class TestValidateConfig:
    """Tests for validate_config function."""

    def test_valid_config(self, sample_config_dict):
        config = Config.from_dict(sample_config_dict)
        errors = validate_config(config)
        assert errors == []

    def test_invalid_version(self):
        config = Config(version=99)
        errors = validate_config(config)
        assert any("version" in e.lower() for e in errors)

    def test_missing_metadata_dataset(self):
        config = Config(metadata_dataset="")
        errors = validate_config(config)
        assert any("metadata_dataset" in e for e in errors)

    def test_empty_dataset_name(self):
        config = Config()
        config.datasets.append(DatasetConfig(name=""))
        errors = validate_config(config)
        assert any("name is required" in e for e in errors)

    def test_invalid_destination_format(self):
        config = Config()
        config.datasets.append(
            DatasetConfig(name="rpool/data", destination="invalid-no-colon")
        )
        errors = validate_config(config)
        assert any("destination" in e for e in errors)

    def test_valid_destination_format(self):
        config = Config()
        config.datasets.append(
            DatasetConfig(name="rpool/data", destination="host:pool/path")
        )
        errors = validate_config(config)
        assert errors == []

    def test_empty_destination_name(self):
        config = Config()
        config.destinations.append(DestinationConfig(name="", host="backup.local"))
        errors = validate_config(config)
        assert any("name is required" in e for e in errors)

    def test_empty_destination_host(self):
        config = Config()
        config.destinations.append(DestinationConfig(name="backup", host=""))
        errors = validate_config(config)
        assert any("host is required" in e for e in errors)


class TestGetDefaultConfig:
    """Tests for get_default_config function."""

    def test_returns_valid_config(self):
        config = get_default_config()
        errors = validate_config(config)
        assert errors == []

    def test_default_values(self):
        config = get_default_config()
        assert config.version == 1
        assert config.metadata_dataset == "rpool/znapzend-full-meta"
        assert config.datasets == []
        assert config.destinations == []

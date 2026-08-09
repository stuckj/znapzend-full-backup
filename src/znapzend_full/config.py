"""
Configuration management for znapzend-full.

Handles loading, saving, and validating the YAML configuration file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# Default paths
DEFAULT_CONFIG_PATH = Path("/etc/znapzend-full/config.yaml")
DEFAULT_METADATA_DATASET = "rpool/znapzend-full-meta"


@dataclass
class RetentionPolicy:
    """Snapshot retention policy."""
    hourly: int = 24
    daily: int = 7
    weekly: int = 4
    monthly: int = 12
    yearly: int = 0

    def to_znapzend_format(self) -> str:
        """Convert to znapzend retention format (e.g., '1h=>15min,1d=>1h,1w=>1d,1m=>1w')."""
        parts = []
        if self.hourly > 0:
            parts.append(f"{self.hourly}h=>1h")
        if self.daily > 0:
            parts.append(f"{self.daily}d=>1d")
        if self.weekly > 0:
            parts.append(f"{self.weekly}w=>1w")
        if self.monthly > 0:
            parts.append(f"{self.monthly}m=>1m")
        if self.yearly > 0:
            parts.append(f"{self.yearly}y=>1y")
        return ",".join(parts) if parts else "1d=>1h"


@dataclass
class DatasetConfig:
    """Configuration for a single ZFS dataset backup."""
    name: str
    recursive: bool = True
    exclude: list[str] = field(default_factory=list)
    destination: str = ""
    retention: RetentionPolicy = field(default_factory=RetentionPolicy)
    enabled: bool = True


@dataclass
class DestinationConfig:
    """Configuration for a remote backup destination."""
    name: str
    host: str
    user: str = "root"
    port: int = 22
    ssh_key: str = ""

    def ssh_uri(self) -> str:
        """Return SSH URI for this destination."""
        return f"ssh://{self.user}@{self.host}:{self.port}"


@dataclass
class AdditionalBackups:
    """Configuration for non-ZFS backups."""
    efi_partitions: list[str] = field(default_factory=list)
    gpt_backup: list[str] = field(default_factory=list)
    zpool_properties: list[str] = field(default_factory=list)
    zfs_properties: list[str] = field(default_factory=list)


@dataclass
class ScheduleConfig:
    """Backup schedule configuration."""
    quiet_hours_start: str = ""  # e.g., "02:00"
    quiet_hours_end: str = ""    # e.g., "06:00"


@dataclass
class Config:
    """Main configuration for znapzend-full."""
    version: int = 1
    metadata_dataset: str = DEFAULT_METADATA_DATASET
    datasets: list[DatasetConfig] = field(default_factory=list)
    additional_backups: AdditionalBackups = field(default_factory=AdditionalBackups)
    destinations: list[DestinationConfig] = field(default_factory=list)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        """Create Config from a dictionary (parsed YAML)."""
        datasets = []
        for ds in data.get("datasets", []):
            retention_data = ds.get("retention", {})
            retention = RetentionPolicy(
                hourly=retention_data.get("hourly", 24),
                daily=retention_data.get("daily", 7),
                weekly=retention_data.get("weekly", 4),
                monthly=retention_data.get("monthly", 12),
                yearly=retention_data.get("yearly", 0),
            )
            datasets.append(DatasetConfig(
                name=ds["name"],
                recursive=ds.get("recursive", True),
                exclude=ds.get("exclude", []),
                destination=ds.get("destination", ""),
                retention=retention,
                enabled=ds.get("enabled", True),
            ))

        destinations = []
        for dest in data.get("destinations", []):
            destinations.append(DestinationConfig(
                name=dest["name"],
                host=dest["host"],
                user=dest.get("user", "root"),
                port=dest.get("port", 22),
                ssh_key=dest.get("ssh_key", ""),
            ))

        additional = data.get("additional_backups", {})
        additional_backups = AdditionalBackups(
            efi_partitions=additional.get("efi_partitions", []),
            gpt_backup=additional.get("gpt_backup", []),
            zpool_properties=additional.get("zpool_properties", []),
            zfs_properties=additional.get("zfs_properties", []),
        )

        schedule_data = data.get("schedule", {})
        quiet_hours = schedule_data.get("quiet_hours", {})
        schedule = ScheduleConfig(
            quiet_hours_start=quiet_hours.get("start", ""),
            quiet_hours_end=quiet_hours.get("end", ""),
        )

        return cls(
            version=data.get("version", 1),
            metadata_dataset=data.get("metadata_dataset", DEFAULT_METADATA_DATASET),
            datasets=datasets,
            additional_backups=additional_backups,
            destinations=destinations,
            schedule=schedule,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert Config to a dictionary for YAML serialization."""
        return {
            "version": self.version,
            "metadata_dataset": self.metadata_dataset,
            "datasets": [
                {
                    "name": ds.name,
                    "recursive": ds.recursive,
                    "exclude": ds.exclude,
                    "destination": ds.destination,
                    "retention": {
                        "hourly": ds.retention.hourly,
                        "daily": ds.retention.daily,
                        "weekly": ds.retention.weekly,
                        "monthly": ds.retention.monthly,
                        "yearly": ds.retention.yearly,
                    },
                    "enabled": ds.enabled,
                }
                for ds in self.datasets
            ],
            "additional_backups": {
                "efi_partitions": self.additional_backups.efi_partitions,
                "gpt_backup": self.additional_backups.gpt_backup,
                "zpool_properties": self.additional_backups.zpool_properties,
                "zfs_properties": self.additional_backups.zfs_properties,
            },
            "destinations": [
                {
                    "name": dest.name,
                    "host": dest.host,
                    "user": dest.user,
                    "port": dest.port,
                    "ssh_key": dest.ssh_key,
                }
                for dest in self.destinations
            ],
            "schedule": {
                "quiet_hours": {
                    "start": self.schedule.quiet_hours_start,
                    "end": self.schedule.quiet_hours_end,
                }
            },
        }


def load_config(path: Path | str | None = None) -> Config:
    """Load configuration from YAML file.

    Args:
        path: Path to config file. Uses DEFAULT_CONFIG_PATH if None.

    Returns:
        Loaded Config object.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        yaml.YAMLError: If config file is invalid YAML.
    """
    if path is None:
        path = DEFAULT_CONFIG_PATH
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with open(path, "r") as f:
        data = yaml.safe_load(f)

    return Config.from_dict(data or {})


def save_config(config: Config, path: Path | str | None = None) -> None:
    """Save configuration to YAML file.

    Args:
        config: Config object to save.
        path: Path to config file. Uses DEFAULT_CONFIG_PATH if None.
    """
    if path is None:
        path = DEFAULT_CONFIG_PATH
    path = Path(path)

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        yaml.dump(config.to_dict(), f, default_flow_style=False, sort_keys=False)


def validate_config(config: Config) -> list[str]:
    """Validate configuration and return list of errors.

    Args:
        config: Config object to validate.

    Returns:
        List of error messages. Empty if valid.
    """
    errors = []

    if config.version != 1:
        errors.append(f"Unsupported config version: {config.version}")

    if not config.metadata_dataset:
        errors.append("metadata_dataset is required")

    for i, ds in enumerate(config.datasets):
        if not ds.name:
            errors.append(f"Dataset {i}: name is required")
        if ds.destination and ":" not in ds.destination:
            errors.append(f"Dataset {ds.name}: destination should be in format 'host:path'")

    for i, dest in enumerate(config.destinations):
        if not dest.name:
            errors.append(f"Destination {i}: name is required")
        if not dest.host:
            errors.append(f"Destination {dest.name}: host is required")

    return errors


def get_default_config() -> Config:
    """Create a default configuration with common settings."""
    return Config(
        version=1,
        metadata_dataset=DEFAULT_METADATA_DATASET,
        datasets=[],
        additional_backups=AdditionalBackups(),
        destinations=[],
        schedule=ScheduleConfig(),
    )

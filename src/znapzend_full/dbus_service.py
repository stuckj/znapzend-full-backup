"""
D-Bus service for znapzend-full.

Provides system-level backup status monitoring and control via D-Bus.
Runs as root to manage ZFS operations.
"""

from __future__ import annotations

import json
import logging
import signal
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

from .config import Config, load_config, save_config, DEFAULT_CONFIG_PATH
from .utils import list_snapshots, list_zpools, list_datasets

logger = logging.getLogger(__name__)

# D-Bus constants
DBUS_BUS_NAME = "org.znapzend.Full"
DBUS_OBJECT_PATH = "/org/znapzend/Full"
DBUS_INTERFACE = "org.znapzend.Full"


class BackupState:
    """Backup state constants."""
    IDLE = "idle"
    BACKING_UP = "backing_up"
    PAUSED = "paused"
    ERROR = "error"


class ZnapzendFullService(dbus.service.Object):
    """D-Bus service for znapzend-full backup management."""

    def __init__(self, bus: dbus.Bus, config_path: Path | None = None):
        """Initialize the D-Bus service.

        Args:
            bus: D-Bus system bus connection.
            config_path: Path to configuration file.
        """
        self.bus_name = dbus.service.BusName(DBUS_BUS_NAME, bus)
        super().__init__(bus, DBUS_OBJECT_PATH)

        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._config: Config | None = None

        # State
        self._state = BackupState.IDLE
        self._current_dataset: str = ""
        self._progress_percent: int = 0
        self._last_backup: str = ""
        self._next_scheduled: str = ""
        self._error_message: str = ""
        self._paused = False

        # Lock for thread-safe state access
        self._lock = threading.Lock()

        # Load initial config
        self._load_config()

        logger.info("ZnapzendFullService initialized")

    def _load_config(self) -> None:
        """Load configuration from file."""
        try:
            if self.config_path.exists():
                self._config = load_config(self.config_path)
                logger.info(f"Loaded configuration from {self.config_path}")
            else:
                logger.warning(f"Config file not found: {self.config_path}")
                self._config = None
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            self._config = None

    def _get_status_dict(self) -> dict[str, Any]:
        """Get current status as a dictionary."""
        with self._lock:
            return {
                "state": self._state,
                "current_dataset": self._current_dataset,
                "progress_percent": self._progress_percent,
                "last_backup": self._last_backup,
                "next_scheduled": self._next_scheduled,
                "error_message": self._error_message,
                "paused": self._paused,
            }

    # --- D-Bus Methods ---

    @dbus.service.method(DBUS_INTERFACE, in_signature="", out_signature="s")
    def GetStatus(self) -> str:
        """Get current backup status as JSON string.

        Returns:
            JSON string with status information.
        """
        return json.dumps(self._get_status_dict())

    @dbus.service.method(DBUS_INTERFACE, in_signature="", out_signature="b")
    def Pause(self) -> bool:
        """Pause backups.

        Returns:
            True if successfully paused.
        """
        with self._lock:
            if self._state == BackupState.BACKING_UP:
                logger.warning("Cannot pause while backup is in progress")
                return False
            self._paused = True
            self._state = BackupState.PAUSED
            logger.info("Backups paused")

        self.StatusChanged(json.dumps(self._get_status_dict()))
        return True

    @dbus.service.method(DBUS_INTERFACE, in_signature="", out_signature="b")
    def Resume(self) -> bool:
        """Resume backups.

        Returns:
            True if successfully resumed.
        """
        with self._lock:
            self._paused = False
            if self._state == BackupState.PAUSED:
                self._state = BackupState.IDLE
            logger.info("Backups resumed")

        self.StatusChanged(json.dumps(self._get_status_dict()))
        return True

    @dbus.service.method(DBUS_INTERFACE, in_signature="", out_signature="b")
    def IsPaused(self) -> bool:
        """Check if backups are paused.

        Returns:
            True if paused.
        """
        with self._lock:
            return self._paused

    @dbus.service.method(DBUS_INTERFACE, in_signature="", out_signature="s")
    def GetConfig(self) -> str:
        """Get current configuration as JSON.

        Returns:
            JSON string with configuration.
        """
        self._load_config()
        if self._config:
            return json.dumps(self._config.to_dict())
        return "{}"

    @dbus.service.method(DBUS_INTERFACE, in_signature="s", out_signature="b")
    def SetConfig(self, config_json: str) -> bool:
        """Update configuration.

        Args:
            config_json: JSON string with new configuration.

        Returns:
            True if successfully saved.
        """
        try:
            data = json.loads(config_json)
            self._config = Config.from_dict(data)
            save_config(self._config, self.config_path)
            logger.info("Configuration updated")
            return True
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False

    @dbus.service.method(DBUS_INTERFACE, in_signature="s", out_signature="s")
    def ListBackups(self, dataset: str) -> str:
        """List available snapshots for a dataset.

        Args:
            dataset: Dataset name (or empty for all).

        Returns:
            JSON string with list of snapshots.
        """
        try:
            if dataset:
                snapshots = list_snapshots(dataset)
            else:
                # List snapshots for all configured datasets
                snapshots = []
                if self._config:
                    for ds in self._config.datasets:
                        snapshots.extend(list_snapshots(ds.name))
            return json.dumps(snapshots)
        except Exception as e:
            logger.error(f"Failed to list backups: {e}")
            return "[]"

    @dbus.service.method(DBUS_INTERFACE, in_signature="", out_signature="b")
    def TriggerBackup(self) -> bool:
        """Manually trigger a backup.

        Returns:
            True if backup was triggered.
        """
        with self._lock:
            if self._paused:
                logger.warning("Cannot trigger backup while paused")
                return False
            if self._state == BackupState.BACKING_UP:
                logger.warning("Backup already in progress")
                return False

        # TODO: Actually trigger znapzend backup
        # For now, just log
        logger.info("Manual backup triggered")
        return True

    @dbus.service.method(DBUS_INTERFACE, in_signature="", out_signature="s")
    def ListPools(self) -> str:
        """List available ZFS pools.

        Returns:
            JSON string with pool information.
        """
        pools = list_zpools()
        return json.dumps([
            {
                "name": p.name,
                "size": p.size,
                "allocated": p.allocated,
                "free": p.free,
                "health": p.health,
            }
            for p in pools
        ])

    @dbus.service.method(DBUS_INTERFACE, in_signature="s", out_signature="s")
    def ListDatasets(self, pool: str) -> str:
        """List datasets in a pool.

        Args:
            pool: Pool name.

        Returns:
            JSON string with dataset information.
        """
        datasets = list_datasets(pool)
        return json.dumps([
            {
                "name": d.name,
                "mountpoint": d.mountpoint,
                "used": d.used,
                "available": d.available,
                "type": d.type,
            }
            for d in datasets
        ])

    # --- Internal notification methods (called by pre/post scripts) ---

    @dbus.service.method(DBUS_INTERFACE, in_signature="", out_signature="")
    def NotifyBackupStarting(self) -> None:
        """Called by pre-backup script to notify backup is starting."""
        with self._lock:
            self._state = BackupState.BACKING_UP
            self._progress_percent = 0
            self._error_message = ""
            logger.info("Backup starting")

        self.StatusChanged(json.dumps(self._get_status_dict()))
        self.BackupStarted("")

    @dbus.service.method(DBUS_INTERFACE, in_signature="b", out_signature="")
    def NotifyBackupCompleted(self, success: bool) -> None:
        """Called by post-backup script to notify backup completed.

        Args:
            success: Whether the backup completed successfully.
        """
        with self._lock:
            if success:
                self._state = BackupState.IDLE
                self._last_backup = datetime.now().isoformat()
                self._error_message = ""
            else:
                self._state = BackupState.ERROR
                self._error_message = "Backup failed"
            self._progress_percent = 100 if success else 0
            self._current_dataset = ""
            logger.info(f"Backup completed: success={success}")

        self.StatusChanged(json.dumps(self._get_status_dict()))
        self.BackupCompleted("", success)

    @dbus.service.method(DBUS_INTERFACE, in_signature="si", out_signature="")
    def NotifyProgress(self, dataset: str, percent: int) -> None:
        """Update backup progress.

        Args:
            dataset: Current dataset being backed up.
            percent: Progress percentage (0-100).
        """
        with self._lock:
            self._current_dataset = dataset
            self._progress_percent = max(0, min(100, percent))

        self.StatusChanged(json.dumps(self._get_status_dict()))

    # --- D-Bus Signals ---

    @dbus.service.signal(DBUS_INTERFACE, signature="s")
    def StatusChanged(self, status_json: str) -> None:
        """Emitted when backup status changes.

        Args:
            status_json: JSON string with new status.
        """
        pass

    @dbus.service.signal(DBUS_INTERFACE, signature="s")
    def BackupStarted(self, dataset: str) -> None:
        """Emitted when a backup starts.

        Args:
            dataset: Dataset being backed up (or empty for all).
        """
        pass

    @dbus.service.signal(DBUS_INTERFACE, signature="sb")
    def BackupCompleted(self, dataset: str, success: bool) -> None:
        """Emitted when a backup completes.

        Args:
            dataset: Dataset that was backed up.
            success: Whether the backup succeeded.
        """
        pass


def main() -> None:
    """Main entry point for the D-Bus service."""
    import argparse

    parser = argparse.ArgumentParser(description="znapzend-full D-Bus service")
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to configuration file",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Setup D-Bus main loop
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    # Connect to system bus
    try:
        bus = dbus.SystemBus()
    except dbus.exceptions.DBusException as e:
        logger.error(f"Failed to connect to system bus: {e}")
        logger.info("Trying session bus for development...")
        bus = dbus.SessionBus()

    # Create service (must remain in scope for D-Bus registration)
    _service = ZnapzendFullService(bus, args.config)  # noqa: F841

    # Setup signal handlers
    loop = GLib.MainLoop()

    def signal_handler(signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}, shutting down")
        loop.quit()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info(f"Starting D-Bus service on {DBUS_BUS_NAME}")

    try:
        loop.run()
    except KeyboardInterrupt:
        pass

    logger.info("D-Bus service stopped")


if __name__ == "__main__":
    main()

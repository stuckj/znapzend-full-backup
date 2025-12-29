"""
System tray application for znapzend-full.

Provides a system tray icon with backup status and controls.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QSystemTrayIcon,
    QMenu,
    QMessageBox,
)

import dbus
import dbus.mainloop.glib

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
    UNKNOWN = "unknown"


class DBusHandler(QObject):
    """Handler for D-Bus signals and communication."""

    status_changed = pyqtSignal(dict)

    def __init__(self, use_session_bus: bool = False):
        super().__init__()
        self.use_session_bus = use_session_bus
        self.connected = False
        self._connect()

    def _connect(self) -> None:
        """Connect to D-Bus."""
        try:
            if self.use_session_bus:
                self.bus = dbus.SessionBus()
            else:
                self.bus = dbus.SystemBus()

            self.proxy = self.bus.get_object(DBUS_BUS_NAME, DBUS_OBJECT_PATH)
            self.interface = dbus.Interface(self.proxy, DBUS_INTERFACE)

            # Connect to status changed signal
            self.bus.add_signal_receiver(
                self._on_status_changed,
                signal_name="StatusChanged",
                dbus_interface=DBUS_INTERFACE,
                bus_name=DBUS_BUS_NAME,
            )

            self.connected = True
            logger.info("Connected to D-Bus service")
        except dbus.exceptions.DBusException as e:
            logger.warning(f"Failed to connect to D-Bus: {e}")
            self.connected = False

    def _on_status_changed(self, status_json: str) -> None:
        """Handle status changed signal from D-Bus."""
        try:
            status = json.loads(status_json)
            self.status_changed.emit(status)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse status: {e}")

    def get_status(self) -> dict[str, Any]:
        """Get current backup status."""
        if not self.connected:
            return {"state": BackupState.UNKNOWN}
        try:
            result = self.interface.GetStatus()
            return json.loads(result)
        except dbus.exceptions.DBusException as e:
            logger.error(f"Failed to get status: {e}")
            return {"state": BackupState.UNKNOWN}

    def pause(self) -> bool:
        """Pause backups."""
        if not self.connected:
            return False
        try:
            return bool(self.interface.Pause())
        except dbus.exceptions.DBusException as e:
            logger.error(f"Failed to pause: {e}")
            return False

    def resume(self) -> bool:
        """Resume backups."""
        if not self.connected:
            return False
        try:
            return bool(self.interface.Resume())
        except dbus.exceptions.DBusException as e:
            logger.error(f"Failed to resume: {e}")
            return False

    def trigger_backup(self) -> bool:
        """Trigger manual backup."""
        if not self.connected:
            return False
        try:
            return bool(self.interface.TriggerBackup())
        except dbus.exceptions.DBusException as e:
            logger.error(f"Failed to trigger backup: {e}")
            return False


class TrayIcon(QSystemTrayIcon):
    """System tray icon for znapzend-full."""

    def __init__(self, use_session_bus: bool = False):
        super().__init__()

        self.use_session_bus = use_session_bus
        self.current_state = BackupState.UNKNOWN

        # Initialize D-Bus handler
        self.dbus_handler = DBusHandler(use_session_bus)
        self.dbus_handler.status_changed.connect(self._on_status_changed)

        # Create icons for different states
        self._create_icons()

        # Create context menu
        self._create_menu()

        # Set initial icon
        self.setIcon(self.icons[BackupState.UNKNOWN])
        self.setToolTip("znapzend-full: Connecting...")

        # Status polling timer (for when D-Bus signals aren't working)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_status)
        self.poll_timer.start(5000)  # Poll every 5 seconds

        # Initial status fetch
        QTimer.singleShot(100, self._poll_status)

    def _create_icons(self) -> None:
        """Create icons for different states."""
        self.icons = {}

        # Create simple colored icons
        # In production, you'd load actual icon files

        def create_circle_icon(color: QColor) -> QIcon:
            """Create a simple circle icon with the given color."""
            pixmap = QPixmap(64, 64)
            pixmap.fill(Qt.GlobalColor.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(4, 4, 56, 56)
            painter.end()

            return QIcon(pixmap)

        self.icons[BackupState.IDLE] = create_circle_icon(QColor(0, 180, 0))       # Green
        self.icons[BackupState.BACKING_UP] = create_circle_icon(QColor(0, 120, 215))  # Blue
        self.icons[BackupState.PAUSED] = create_circle_icon(QColor(255, 180, 0))    # Yellow
        self.icons[BackupState.ERROR] = create_circle_icon(QColor(220, 0, 0))       # Red
        self.icons[BackupState.UNKNOWN] = create_circle_icon(QColor(128, 128, 128)) # Gray

    def _create_menu(self) -> None:
        """Create the context menu."""
        self.menu = QMenu()

        # Status (non-clickable)
        self.status_action = QAction("Status: Unknown")
        self.status_action.setEnabled(False)
        self.menu.addAction(self.status_action)

        self.menu.addSeparator()

        # Pause/Resume
        self.pause_action = QAction("Pause Backups")
        self.pause_action.triggered.connect(self._on_pause_clicked)
        self.menu.addAction(self.pause_action)

        # Backup Now
        self.backup_action = QAction("Backup Now")
        self.backup_action.triggered.connect(self._on_backup_clicked)
        self.menu.addAction(self.backup_action)

        self.menu.addSeparator()

        # View History
        history_action = QAction("View Backup History")
        history_action.triggered.connect(self._on_history_clicked)
        self.menu.addAction(history_action)

        self.menu.addSeparator()

        # Configure
        configure_action = QAction("Configure...")
        configure_action.triggered.connect(self._on_configure_clicked)
        self.menu.addAction(configure_action)

        self.menu.addSeparator()

        # Quit
        quit_action = QAction("Quit")
        quit_action.triggered.connect(QApplication.quit)
        self.menu.addAction(quit_action)

        self.setContextMenu(self.menu)

    def _update_ui(self, status: dict[str, Any]) -> None:
        """Update UI based on status."""
        state = status.get("state", BackupState.UNKNOWN)
        self.current_state = state

        # Update icon
        icon = self.icons.get(state, self.icons[BackupState.UNKNOWN])
        self.setIcon(icon)

        # Update tooltip
        tooltip_parts = ["znapzend-full"]
        if state == BackupState.IDLE:
            tooltip_parts.append("Idle")
            if status.get("last_backup"):
                tooltip_parts.append(f"Last backup: {status['last_backup']}")
        elif state == BackupState.BACKING_UP:
            tooltip_parts.append("Backup in progress")
            if status.get("current_dataset"):
                tooltip_parts.append(f"Dataset: {status['current_dataset']}")
            if status.get("progress_percent"):
                tooltip_parts.append(f"Progress: {status['progress_percent']}%")
        elif state == BackupState.PAUSED:
            tooltip_parts.append("Paused")
        elif state == BackupState.ERROR:
            tooltip_parts.append("Error")
            if status.get("error_message"):
                tooltip_parts.append(status["error_message"])
        else:
            tooltip_parts.append("Status unknown")

        self.setToolTip("\n".join(tooltip_parts))

        # Update status action
        if state == BackupState.IDLE:
            self.status_action.setText("Status: Idle")
        elif state == BackupState.BACKING_UP:
            progress = status.get("progress_percent", 0)
            self.status_action.setText(f"Status: Backing up ({progress}%)")
        elif state == BackupState.PAUSED:
            self.status_action.setText("Status: Paused")
        elif state == BackupState.ERROR:
            self.status_action.setText("Status: Error")
        else:
            self.status_action.setText("Status: Unknown")

        # Update pause/resume button
        if status.get("paused", False):
            self.pause_action.setText("Resume Backups")
        else:
            self.pause_action.setText("Pause Backups")

        # Disable backup button if already backing up or paused
        self.backup_action.setEnabled(
            state not in (BackupState.BACKING_UP, BackupState.PAUSED)
        )

    def _on_status_changed(self, status: dict[str, Any]) -> None:
        """Handle status change from D-Bus signal."""
        self._update_ui(status)

    def _poll_status(self) -> None:
        """Poll status from D-Bus."""
        if self.dbus_handler.connected:
            status = self.dbus_handler.get_status()
            self._update_ui(status)
        else:
            # Try to reconnect
            self.dbus_handler._connect()
            if not self.dbus_handler.connected:
                self._update_ui({"state": BackupState.UNKNOWN})

    def _on_pause_clicked(self) -> None:
        """Handle pause/resume button click."""
        status = self.dbus_handler.get_status()
        if status.get("paused", False):
            if self.dbus_handler.resume():
                self.showMessage("znapzend-full", "Backups resumed")
            else:
                self.showMessage("znapzend-full", "Failed to resume backups",
                               QSystemTrayIcon.MessageIcon.Warning)
        else:
            if self.dbus_handler.pause():
                self.showMessage("znapzend-full", "Backups paused")
            else:
                self.showMessage("znapzend-full", "Failed to pause backups",
                               QSystemTrayIcon.MessageIcon.Warning)

        # Refresh status
        self._poll_status()

    def _on_backup_clicked(self) -> None:
        """Handle backup now button click."""
        if self.dbus_handler.trigger_backup():
            self.showMessage("znapzend-full", "Backup triggered")
        else:
            self.showMessage("znapzend-full", "Failed to trigger backup",
                           QSystemTrayIcon.MessageIcon.Warning)

        self._poll_status()

    def _on_history_clicked(self) -> None:
        """Handle view history button click."""
        # TODO: Open history dialog or use CLI
        QMessageBox.information(
            None,
            "Backup History",
            "Use 'znapzend-full-ctl list' to view backup history.",
        )

    def _on_configure_clicked(self) -> None:
        """Handle configure button click."""
        # Import here to avoid circular imports
        from .config_dialog import ConfigDialog

        dialog = ConfigDialog(use_session_bus=self.use_session_bus)
        dialog.exec()


def main() -> int:
    """Main entry point for tray application."""
    import argparse

    parser = argparse.ArgumentParser(description="znapzend-full system tray")
    parser.add_argument(
        "--session-bus",
        action="store_true",
        help="Use session D-Bus (for development)",
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

    # Initialize D-Bus main loop for GLib (needed for signals)
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    # Create application
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("znapzend-full")
    app.setApplicationDisplayName("ZnapZend Full Backup")

    # Check if system tray is available
    if not QSystemTrayIcon.isSystemTrayAvailable():
        logger.error("System tray not available")
        return 1

    # Create tray icon
    tray = TrayIcon(use_session_bus=args.session_bus)
    tray.show()

    logger.info("Tray application started")

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

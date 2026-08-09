"""
Configuration dialog for znapzend-full.

Provides a tabbed dialog for configuring backup settings.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QLabel,
    QPushButton,
    QLineEdit,
    QSpinBox,
    QCheckBox,
    QTreeWidget,
    QTreeWidgetItem,
    QListWidget,
    QListWidgetItem,
    QGroupBox,
    QFormLayout,
    QMessageBox,
    QDialogButtonBox,
    QSplitter,
)

from znapzend_full.config import (
    Config,
    DatasetConfig,
    DestinationConfig,
    RetentionPolicy,
    load_config,
    save_config,
    validate_config,
    DEFAULT_CONFIG_PATH,
)
from znapzend_full.utils import list_zpools, list_datasets, find_efi_partitions, find_gpt_disks

logger = logging.getLogger(__name__)

# D-Bus constants
DBUS_BUS_NAME = "org.znapzend.Full"
DBUS_OBJECT_PATH = "/org/znapzend/Full"
DBUS_INTERFACE = "org.znapzend.Full"


class DatasetTab(QWidget):
    """Tab for configuring ZFS dataset backups."""

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self._setup_ui()
        self._load_datasets()

    def _setup_ui(self) -> None:
        """Setup the UI."""
        layout = QVBoxLayout(self)

        # Splitter for tree and details
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Dataset tree
        tree_widget = QWidget()
        tree_layout = QVBoxLayout(tree_widget)
        tree_layout.setContentsMargins(0, 0, 0, 0)

        tree_label = QLabel("Available Datasets:")
        tree_layout.addWidget(tree_label)

        self.dataset_tree = QTreeWidget()
        self.dataset_tree.setHeaderLabels(["Dataset", "Mountpoint", "Used"])
        self.dataset_tree.itemChanged.connect(self._on_item_changed)
        self.dataset_tree.currentItemChanged.connect(self._on_selection_changed)
        tree_layout.addWidget(self.dataset_tree)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_datasets)
        tree_layout.addWidget(refresh_btn)

        splitter.addWidget(tree_widget)

        # Details panel
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(0, 0, 0, 0)

        details_label = QLabel("Dataset Settings:")
        details_layout.addWidget(details_label)

        self.details_group = QGroupBox("No dataset selected")
        self.details_group.setEnabled(False)
        details_form = QFormLayout(self.details_group)

        self.recursive_check = QCheckBox("Recursive backup")
        details_form.addRow("", self.recursive_check)

        self.destination_edit = QLineEdit()
        self.destination_edit.setPlaceholderText("backup-server:tank/backups/...")
        details_form.addRow("Destination:", self.destination_edit)

        # Retention policy
        retention_group = QGroupBox("Retention Policy")
        retention_layout = QFormLayout(retention_group)

        self.hourly_spin = QSpinBox()
        self.hourly_spin.setRange(0, 168)
        self.hourly_spin.setValue(24)
        retention_layout.addRow("Hourly:", self.hourly_spin)

        self.daily_spin = QSpinBox()
        self.daily_spin.setRange(0, 365)
        self.daily_spin.setValue(7)
        retention_layout.addRow("Daily:", self.daily_spin)

        self.weekly_spin = QSpinBox()
        self.weekly_spin.setRange(0, 52)
        self.weekly_spin.setValue(4)
        retention_layout.addRow("Weekly:", self.weekly_spin)

        self.monthly_spin = QSpinBox()
        self.monthly_spin.setRange(0, 60)
        self.monthly_spin.setValue(12)
        retention_layout.addRow("Monthly:", self.monthly_spin)

        self.yearly_spin = QSpinBox()
        self.yearly_spin.setRange(0, 10)
        self.yearly_spin.setValue(0)
        retention_layout.addRow("Yearly:", self.yearly_spin)

        details_form.addRow(retention_group)

        details_layout.addWidget(self.details_group)
        details_layout.addStretch()

        splitter.addWidget(details_widget)
        splitter.setSizes([400, 300])

        layout.addWidget(splitter)

    def _load_datasets(self) -> None:
        """Load available datasets from system."""
        self.dataset_tree.clear()

        # Get configured dataset names for checking
        configured = {ds.name for ds in self.config.datasets}

        # Load pools and datasets
        pools = list_zpools()
        for pool in pools:
            pool_item = QTreeWidgetItem([pool.name, "", ""])
            pool_item.setFlags(pool_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            pool_item.setCheckState(0, Qt.CheckState.Unchecked)
            pool_item.setData(0, Qt.ItemDataRole.UserRole, pool.name)

            # Load datasets for this pool
            datasets = list_datasets(pool.name)
            for ds in datasets:
                if ds.type != "filesystem":
                    continue

                ds_item = QTreeWidgetItem([
                    ds.name,
                    ds.mountpoint or "",
                    self._format_size(ds.used),
                ])
                ds_item.setFlags(ds_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                ds_item.setData(0, Qt.ItemDataRole.UserRole, ds.name)

                # Check if configured
                if ds.name in configured:
                    ds_item.setCheckState(0, Qt.CheckState.Checked)
                else:
                    ds_item.setCheckState(0, Qt.CheckState.Unchecked)

                pool_item.addChild(ds_item)

            self.dataset_tree.addTopLevelItem(pool_item)
            pool_item.setExpanded(True)

        self.dataset_tree.resizeColumnToContents(0)

    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human-readable."""
        for unit in ["B", "K", "M", "G", "T"]:
            if abs(size_bytes) < 1024:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f}P"

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle checkbox changes."""
        if column != 0:
            return

        dataset_name = item.data(0, Qt.ItemDataRole.UserRole)
        checked = item.checkState(0) == Qt.CheckState.Checked

        if checked:
            # Add to config if not present
            if not any(ds.name == dataset_name for ds in self.config.datasets):
                self.config.datasets.append(DatasetConfig(name=dataset_name))
        else:
            # Remove from config
            self.config.datasets = [
                ds for ds in self.config.datasets if ds.name != dataset_name
            ]

    def _on_selection_changed(
        self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None
    ) -> None:
        """Handle selection change."""
        if not current:
            self.details_group.setTitle("No dataset selected")
            self.details_group.setEnabled(False)
            return

        dataset_name = current.data(0, Qt.ItemDataRole.UserRole)
        if not dataset_name:
            return

        self.details_group.setTitle(dataset_name)
        self.details_group.setEnabled(True)

        # Find config for this dataset
        ds_config = next(
            (ds for ds in self.config.datasets if ds.name == dataset_name),
            None
        )

        if ds_config:
            self.recursive_check.setChecked(ds_config.recursive)
            self.destination_edit.setText(ds_config.destination)
            self.hourly_spin.setValue(ds_config.retention.hourly)
            self.daily_spin.setValue(ds_config.retention.daily)
            self.weekly_spin.setValue(ds_config.retention.weekly)
            self.monthly_spin.setValue(ds_config.retention.monthly)
            self.yearly_spin.setValue(ds_config.retention.yearly)
        else:
            # Defaults
            self.recursive_check.setChecked(True)
            self.destination_edit.setText("")
            self.hourly_spin.setValue(24)
            self.daily_spin.setValue(7)
            self.weekly_spin.setValue(4)
            self.monthly_spin.setValue(12)
            self.yearly_spin.setValue(0)

    def save_current_selection(self) -> None:
        """Save current selection to config."""
        current = self.dataset_tree.currentItem()
        if not current:
            return

        dataset_name = current.data(0, Qt.ItemDataRole.UserRole)
        if not dataset_name:
            return

        # Find or create config
        ds_config = next(
            (ds for ds in self.config.datasets if ds.name == dataset_name),
            None
        )

        if ds_config:
            ds_config.recursive = self.recursive_check.isChecked()
            ds_config.destination = self.destination_edit.text()
            ds_config.retention = RetentionPolicy(
                hourly=self.hourly_spin.value(),
                daily=self.daily_spin.value(),
                weekly=self.weekly_spin.value(),
                monthly=self.monthly_spin.value(),
                yearly=self.yearly_spin.value(),
            )


class AdditionalBackupsTab(QWidget):
    """Tab for configuring additional (non-ZFS) backups."""

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self._setup_ui()
        self._load_devices()

    def _setup_ui(self) -> None:
        """Setup the UI."""
        layout = QVBoxLayout(self)

        # EFI Partitions
        efi_group = QGroupBox("EFI Partitions")
        efi_layout = QVBoxLayout(efi_group)

        efi_label = QLabel("Select EFI partitions to backup:")
        efi_layout.addWidget(efi_label)

        self.efi_list = QListWidget()
        efi_layout.addWidget(self.efi_list)

        layout.addWidget(efi_group)

        # GPT Disks
        gpt_group = QGroupBox("GPT Partition Tables")
        gpt_layout = QVBoxLayout(gpt_group)

        gpt_label = QLabel("Select disks to backup GPT layout:")
        gpt_layout.addWidget(gpt_label)

        self.gpt_list = QListWidget()
        gpt_layout.addWidget(self.gpt_list)

        layout.addWidget(gpt_group)

        # ZPool/ZFS Properties
        props_group = QGroupBox("ZFS Properties")
        props_layout = QVBoxLayout(props_group)

        props_label = QLabel(
            "ZFS and zpool properties will be backed up for all configured pools."
        )
        props_layout.addWidget(props_label)

        layout.addWidget(props_group)

        # Refresh button
        refresh_btn = QPushButton("Refresh Devices")
        refresh_btn.clicked.connect(self._load_devices)
        layout.addWidget(refresh_btn)

    def _load_devices(self) -> None:
        """Load available devices."""
        # EFI partitions
        self.efi_list.clear()
        configured_efi = set(self.config.additional_backups.efi_partitions)

        for partition in find_efi_partitions():
            item = QListWidgetItem(partition)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if partition in configured_efi:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            self.efi_list.addItem(item)

        # GPT disks
        self.gpt_list.clear()
        configured_gpt = set(self.config.additional_backups.gpt_backup)

        for disk in find_gpt_disks():
            item = QListWidgetItem(disk)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if disk in configured_gpt:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            self.gpt_list.addItem(item)

    def save_to_config(self) -> None:
        """Save selections to config."""
        # EFI partitions
        efi_partitions = []
        for i in range(self.efi_list.count()):
            item = self.efi_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                efi_partitions.append(item.text())
        self.config.additional_backups.efi_partitions = efi_partitions

        # GPT disks
        gpt_disks = []
        for i in range(self.gpt_list.count()):
            item = self.gpt_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                gpt_disks.append(item.text())
        self.config.additional_backups.gpt_backup = gpt_disks


class DestinationsTab(QWidget):
    """Tab for configuring backup destinations."""

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self._setup_ui()
        self._load_destinations()

    def _setup_ui(self) -> None:
        """Setup the UI."""
        layout = QHBoxLayout(self)

        # Destination list
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)

        list_label = QLabel("Destinations:")
        list_layout.addWidget(list_label)

        self.dest_list = QListWidget()
        self.dest_list.currentRowChanged.connect(self._on_selection_changed)
        list_layout.addWidget(self.dest_list)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_destination)
        btn_layout.addWidget(add_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_destination)
        btn_layout.addWidget(remove_btn)

        list_layout.addLayout(btn_layout)
        layout.addWidget(list_widget)

        # Details panel
        self.details_group = QGroupBox("Destination Settings")
        self.details_group.setEnabled(False)
        details_form = QFormLayout(self.details_group)

        self.name_edit = QLineEdit()
        details_form.addRow("Name:", self.name_edit)

        self.host_edit = QLineEdit()
        details_form.addRow("Host:", self.host_edit)

        self.user_edit = QLineEdit()
        self.user_edit.setText("root")
        details_form.addRow("User:", self.user_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(22)
        details_form.addRow("Port:", self.port_spin)

        self.ssh_key_edit = QLineEdit()
        self.ssh_key_edit.setPlaceholderText("~/.ssh/id_rsa")
        details_form.addRow("SSH Key:", self.ssh_key_edit)

        test_btn = QPushButton("Test Connection")
        test_btn.clicked.connect(self._test_connection)
        details_form.addRow("", test_btn)

        layout.addWidget(self.details_group)

    def _load_destinations(self) -> None:
        """Load destinations from config."""
        self.dest_list.clear()
        for dest in self.config.destinations:
            self.dest_list.addItem(dest.name)

    def _on_selection_changed(self, row: int) -> None:
        """Handle selection change."""
        if row < 0 or row >= len(self.config.destinations):
            self.details_group.setEnabled(False)
            return

        self.details_group.setEnabled(True)
        dest = self.config.destinations[row]

        self.name_edit.setText(dest.name)
        self.host_edit.setText(dest.host)
        self.user_edit.setText(dest.user)
        self.port_spin.setValue(dest.port)
        self.ssh_key_edit.setText(dest.ssh_key)

    def _add_destination(self) -> None:
        """Add a new destination."""
        new_dest = DestinationConfig(
            name=f"destination-{len(self.config.destinations) + 1}",
            host="",
        )
        self.config.destinations.append(new_dest)
        self.dest_list.addItem(new_dest.name)
        self.dest_list.setCurrentRow(len(self.config.destinations) - 1)

    def _remove_destination(self) -> None:
        """Remove selected destination."""
        row = self.dest_list.currentRow()
        if row >= 0:
            del self.config.destinations[row]
            self.dest_list.takeItem(row)

    def _test_connection(self) -> None:
        """Test SSH connection to destination."""
        import subprocess

        host = self.host_edit.text()
        user = self.user_edit.text()
        port = self.port_spin.value()
        ssh_key = self.ssh_key_edit.text()

        if not host:
            QMessageBox.warning(self, "Error", "Host is required")
            return

        cmd = ["ssh"]
        if ssh_key:
            cmd.extend(["-i", ssh_key])
        cmd.extend([
            "-p", str(port),
            "-o", "ConnectTimeout=10",
            "-o", "BatchMode=yes",
            f"{user}@{host}",
            "echo", "Connection successful"
        ])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                QMessageBox.information(self, "Success", "Connection successful!")
            else:
                QMessageBox.warning(
                    self, "Failed",
                    f"Connection failed:\n{result.stderr}"
                )
        except subprocess.TimeoutExpired:
            QMessageBox.warning(self, "Timeout", "Connection timed out")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error: {e}")

    def save_to_config(self) -> None:
        """Save current selection to config."""
        row = self.dest_list.currentRow()
        if row >= 0 and row < len(self.config.destinations):
            dest = self.config.destinations[row]
            dest.name = self.name_edit.text()
            dest.host = self.host_edit.text()
            dest.user = self.user_edit.text()
            dest.port = self.port_spin.value()
            dest.ssh_key = self.ssh_key_edit.text()


class ConfigDialog(QDialog):
    """Main configuration dialog."""

    def __init__(
        self,
        config_path: Path | None = None,
        use_session_bus: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.use_session_bus = use_session_bus

        # Load config
        if self.config_path.exists():
            self.config = load_config(self.config_path)
        else:
            from znapzend_full.config import get_default_config
            self.config = get_default_config()

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the UI."""
        self.setWindowTitle("znapzend-full Configuration")
        self.setMinimumSize(800, 600)

        layout = QVBoxLayout(self)

        # Tab widget
        self.tabs = QTabWidget()

        # Datasets tab
        self.dataset_tab = DatasetTab(self.config)
        self.tabs.addTab(self.dataset_tab, "ZFS Datasets")

        # Additional backups tab
        self.additional_tab = AdditionalBackupsTab(self.config)
        self.tabs.addTab(self.additional_tab, "Additional Backups")

        # Destinations tab
        self.dest_tab = DestinationsTab(self.config)
        self.tabs.addTab(self.dest_tab, "Destinations")

        layout.addWidget(self.tabs)

        # Button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._save_and_close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _save_and_close(self) -> None:
        """Save configuration and close dialog."""
        # Save current tab selections
        self.dataset_tab.save_current_selection()
        self.additional_tab.save_to_config()
        self.dest_tab.save_to_config()

        # Validate
        errors = validate_config(self.config)
        if errors:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Configuration has errors:\n" + "\n".join(f"- {e}" for e in errors)
            )
            return

        # Ensure directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        # Save
        try:
            save_config(self.config, self.config_path)
            QMessageBox.information(
                self,
                "Saved",
                f"Configuration saved to {self.config_path}"
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save configuration: {e}"
            )

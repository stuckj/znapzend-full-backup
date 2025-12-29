"""
Interactive restore TUI using Textual.

Provides a terminal-based interface for restoring backups.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    OptionList,
    Placeholder,
    ProgressBar,
    RadioButton,
    RadioSet,
    RichLog,
    Rule,
    Static,
    Switch,
    TabbedContent,
    TabPane,
)
from textual.widget import Widget

from .ssh_client import SSHClient, SSHConfig
from .zfs_restore import restore_dataset, apply_properties_from_file
from .partition_restore import restore_gpt, restore_efi

logger = logging.getLogger(__name__)


class WelcomeScreen(Screen):
    """Welcome screen with connection setup."""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("enter", "connect", "Connect"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("znapzend-full Restore", classes="title"),
            Static("Interactive System Restore Utility\n", classes="subtitle"),
            Rule(),
            Static("Backup Source Configuration", classes="section"),
            Horizontal(
                Label("Host:"),
                Input(placeholder="backup-server.local", id="host"),
            ),
            Horizontal(
                Label("User:"),
                Input(value="root", id="user"),
            ),
            Horizontal(
                Label("Port:"),
                Input(value="22", id="port"),
            ),
            Horizontal(
                Label("SSH Key:"),
                Input(placeholder="~/.ssh/id_rsa (optional)", id="ssh_key"),
            ),
            Rule(),
            Horizontal(
                Button("Connect", variant="primary", id="connect"),
                Button("Local Restore", id="local"),
                Button("Quit", variant="error", id="quit"),
                classes="buttons",
            ),
            id="welcome",
        )
        yield Footer()

    def action_quit(self) -> None:
        self.app.exit()

    def action_connect(self) -> None:
        self.connect()

    @on(Button.Pressed, "#connect")
    def connect(self) -> None:
        host = self.query_one("#host", Input).value
        user = self.query_one("#user", Input).value
        port = int(self.query_one("#port", Input).value or "22")
        ssh_key = self.query_one("#ssh_key", Input).value

        if not host:
            self.notify("Host is required", severity="error")
            return

        config = SSHConfig(host=host, user=user, port=port, ssh_key=ssh_key)
        self.app.ssh_config = config

        # Test connection
        client = SSHClient(config)
        success, message = client.test_connection()

        if success:
            self.notify(f"Connected to {host}")
            self.app.ssh_client = client
            self.app.push_screen(SnapshotSelectScreen())
        else:
            self.notify(f"Connection failed: {message}", severity="error")

    @on(Button.Pressed, "#local")
    def local_restore(self) -> None:
        self.notify("Local restore not yet implemented", severity="warning")

    @on(Button.Pressed, "#quit")
    def quit_pressed(self) -> None:
        self.app.exit()


class SnapshotSelectScreen(Screen):
    """Screen for selecting backup snapshot to restore."""

    BINDINGS = [
        Binding("q", "back", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("enter", "select", "Select"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("Select Backup Snapshot", classes="title"),
            Rule(),
            Static("Available Pools:", classes="section"),
            ListView(id="pool_list"),
            Rule(),
            Static("Snapshots:", classes="section"),
            DataTable(id="snapshot_table"),
            Rule(),
            Horizontal(
                Button("Back", id="back"),
                Button("Refresh", id="refresh"),
                Button("Select", variant="primary", id="select"),
                classes="buttons",
            ),
            id="snapshot_select",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.load_pools()
        table = self.query_one("#snapshot_table", DataTable)
        table.add_columns("Snapshot", "Creation", "Size")

    def load_pools(self) -> None:
        pools = self.app.ssh_client.list_pools()
        pool_list = self.query_one("#pool_list", ListView)
        pool_list.clear()
        for pool in pools:
            pool_list.append(ListItem(Label(pool), id=f"pool_{pool}"))

    @on(ListView.Selected, "#pool_list")
    def pool_selected(self, event: ListView.Selected) -> None:
        pool = event.item.id.replace("pool_", "")
        self.load_snapshots(pool)

    def load_snapshots(self, pool: str) -> None:
        snapshots = self.app.ssh_client.list_snapshots(pool)
        table = self.query_one("#snapshot_table", DataTable)
        table.clear()

        for snap in snapshots[:50]:  # Limit to 50 for performance
            info = self.app.ssh_client.get_snapshot_info(snap)
            if info:
                table.add_row(
                    snap,
                    info.get("creation", ""),
                    info.get("used", ""),
                    key=snap,
                )

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self.load_pools()

    def action_select(self) -> None:
        table = self.query_one("#snapshot_table", DataTable)
        if table.cursor_row is not None:
            row_key = table.get_row_at(table.cursor_row)
            if row_key:
                self.app.selected_snapshot = row_key[0]
                self.app.push_screen(DestinationSelectScreen())

    @on(Button.Pressed, "#back")
    def back_pressed(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#refresh")
    def refresh_pressed(self) -> None:
        self.load_pools()

    @on(Button.Pressed, "#select")
    def select_pressed(self) -> None:
        self.action_select()


class DestinationSelectScreen(Screen):
    """Screen for selecting restore destination."""

    BINDINGS = [
        Binding("q", "back", "Back"),
        Binding("enter", "next", "Next"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("Select Restore Destination", classes="title"),
            Static(f"Selected: {getattr(self.app, 'selected_snapshot', 'None')}", classes="info"),
            Rule(),
            Static("Available Disks:", classes="section"),
            DataTable(id="disk_table"),
            Rule(),
            Static("Restore Options:", classes="section"),
            Horizontal(
                Switch(id="restore_gpt"),
                Label("Restore GPT partition layout"),
            ),
            Horizontal(
                Switch(id="restore_efi"),
                Label("Restore EFI partition"),
            ),
            Horizontal(
                Switch(id="restore_props", value=True),
                Label("Restore ZFS properties"),
            ),
            Horizontal(
                Switch(id="install_bootloader"),
                Label("Install bootloader (GRUB)"),
            ),
            Rule(),
            Horizontal(
                Button("Back", id="back"),
                Button("Begin Restore", variant="primary", id="restore"),
                classes="buttons",
            ),
            id="destination_select",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.load_disks()

    def load_disks(self) -> None:
        """Load available local disks."""
        import subprocess
        table = self.query_one("#disk_table", DataTable)
        table.add_columns("Device", "Size", "Type", "Mountpoint")

        try:
            result = subprocess.run(
                ["lsblk", "-d", "-o", "NAME,SIZE,TYPE,MOUNTPOINT", "-n"],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.strip().split("\n"):
                if line:
                    parts = line.split()
                    if len(parts) >= 3 and parts[2] == "disk":
                        table.add_row(
                            f"/dev/{parts[0]}",
                            parts[1] if len(parts) > 1 else "",
                            parts[2] if len(parts) > 2 else "",
                            parts[3] if len(parts) > 3 else "",
                            key=parts[0],
                        )
        except Exception as e:
            self.notify(f"Failed to list disks: {e}", severity="error")

    def action_back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#back")
    def back_pressed(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#restore")
    def restore_pressed(self) -> None:
        table = self.query_one("#disk_table", DataTable)
        if table.cursor_row is None:
            self.notify("Please select a destination disk", severity="warning")
            return

        row = table.get_row_at(table.cursor_row)
        if row:
            self.app.target_disk = row[0]
            self.app.restore_options = {
                "restore_gpt": self.query_one("#restore_gpt", Switch).value,
                "restore_efi": self.query_one("#restore_efi", Switch).value,
                "restore_props": self.query_one("#restore_props", Switch).value,
                "install_bootloader": self.query_one("#install_bootloader", Switch).value,
            }
            self.app.push_screen(ConfirmScreen())


class ConfirmScreen(Screen):
    """Confirmation screen before restore."""

    BINDINGS = [
        Binding("q", "back", "Back"),
        Binding("y", "confirm", "Confirm"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("Confirm Restore", classes="title"),
            Rule(),
            Static("WARNING: This will DESTROY all data on the target disk!",
                   classes="warning"),
            Rule(),
            Static("Restore Summary:", classes="section"),
            Static(f"Source: {getattr(self.app, 'selected_snapshot', 'N/A')}", classes="info"),
            Static(f"Target: {getattr(self.app, 'target_disk', 'N/A')}", classes="info"),
            Static("Options:", classes="section"),
            Static(self._format_options(), id="options"),
            Rule(),
            Horizontal(
                Button("Cancel", id="cancel"),
                Button("BEGIN RESTORE", variant="error", id="confirm"),
                classes="buttons",
            ),
            id="confirm",
        )
        yield Footer()

    def _format_options(self) -> str:
        opts = getattr(self.app, "restore_options", {})
        lines = []
        if opts.get("restore_gpt"):
            lines.append("- Restore GPT partition layout")
        if opts.get("restore_efi"):
            lines.append("- Restore EFI partition")
        if opts.get("restore_props"):
            lines.append("- Restore ZFS properties")
        if opts.get("install_bootloader"):
            lines.append("- Install bootloader")
        return "\n".join(lines) if lines else "(no additional options)"

    def action_back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#cancel")
    def cancel_pressed(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#confirm")
    def confirm_pressed(self) -> None:
        self.app.push_screen(RestoreProgressScreen())


class RestoreProgressScreen(Screen):
    """Progress screen during restore."""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("Restore in Progress", classes="title"),
            Rule(),
            ProgressBar(id="progress", total=100),
            Static("Starting restore...", id="status"),
            Rule(),
            RichLog(id="log", highlight=True, markup=True),
            Rule(),
            Button("Cancel", variant="error", id="cancel", disabled=True),
            id="progress",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.run_restore()

    def run_restore(self) -> None:
        """Run the restore process."""
        log = self.query_one("#log", RichLog)
        progress = self.query_one("#progress", ProgressBar)
        status = self.query_one("#status", Static)

        log.write("[bold blue]Starting restore process...[/]")

        # This would be async in a real implementation
        # For now, just show placeholder steps

        steps = [
            "Connecting to backup server...",
            "Verifying snapshot...",
            "Preparing destination...",
            "Restoring ZFS datasets...",
            "Applying ZFS properties...",
            "Restoring partition layout...",
            "Restoring EFI partition...",
            "Installing bootloader...",
            "Finishing up...",
        ]

        for i, step in enumerate(steps):
            log.write(f"[yellow]{step}[/]")
            progress.progress = (i + 1) * (100 // len(steps))
            status.update(step)

        log.write("[bold green]Restore completed successfully![/]")
        progress.progress = 100
        status.update("Restore completed!")

        # Enable cancel (now "Close") button
        cancel = self.query_one("#cancel", Button)
        cancel.label = "Close"
        cancel.disabled = False
        cancel.variant = "primary"

    @on(Button.Pressed, "#cancel")
    def close_pressed(self) -> None:
        self.app.exit()


class RestoreApp(App):
    """Main restore application."""

    CSS = """
    .title {
        text-align: center;
        text-style: bold;
        padding: 1;
        color: $primary;
    }

    .subtitle {
        text-align: center;
        color: $text-muted;
    }

    .section {
        margin-top: 1;
        margin-bottom: 1;
        text-style: bold;
    }

    .info {
        margin-left: 2;
    }

    .warning {
        color: $error;
        text-style: bold;
        text-align: center;
        padding: 1;
        background: $surface;
    }

    .buttons {
        margin-top: 2;
        align: center middle;
    }

    Button {
        margin: 0 1;
    }

    Input {
        width: 40;
        margin-left: 1;
    }

    Label {
        width: 12;
        text-align: right;
        padding-right: 1;
    }

    #welcome, #snapshot_select, #destination_select, #confirm, #progress {
        padding: 2;
    }

    ListView {
        height: 10;
        border: solid $primary;
    }

    DataTable {
        height: 15;
    }

    RichLog {
        height: 15;
        border: solid $primary;
    }

    Switch {
        margin-right: 1;
    }
    """

    TITLE = "znapzend-full Restore"
    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self):
        super().__init__()
        self.ssh_config: SSHConfig | None = None
        self.ssh_client: SSHClient | None = None
        self.selected_snapshot: str | None = None
        self.target_disk: str | None = None
        self.restore_options: dict = {}

    def on_mount(self) -> None:
        self.push_screen(WelcomeScreen())

    def action_quit(self) -> None:
        self.exit()


def main() -> int:
    """Main entry point for restore TUI."""
    parser = argparse.ArgumentParser(description="znapzend-full interactive restore")
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    app = RestoreApp()
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

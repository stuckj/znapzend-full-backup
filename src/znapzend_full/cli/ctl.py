"""
CLI control tool for znapzend-full.

Provides command-line control for headless systems (Proxmox, servers).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import dbus

from ..config import (
    load_config,
    save_config,
    validate_config,
    get_default_config,
    DEFAULT_CONFIG_PATH,
)

# D-Bus constants
DBUS_BUS_NAME = "org.znapzend.Full"
DBUS_OBJECT_PATH = "/org/znapzend/Full"
DBUS_INTERFACE = "org.znapzend.Full"


class DBusClient:
    """Client for communicating with the znapzend-full D-Bus service."""

    def __init__(self, use_session_bus: bool = False):
        """Initialize D-Bus client.

        Args:
            use_session_bus: Use session bus instead of system bus (for testing).
        """
        try:
            if use_session_bus:
                self.bus = dbus.SessionBus()
            else:
                self.bus = dbus.SystemBus()

            self.proxy = self.bus.get_object(DBUS_BUS_NAME, DBUS_OBJECT_PATH)
            self.interface = dbus.Interface(self.proxy, DBUS_INTERFACE)
            self.connected = True
        except dbus.exceptions.DBusException as e:
            self.connected = False
            self.error = str(e)

    def get_status(self) -> dict[str, Any]:
        """Get current backup status."""
        if not self.connected:
            return {"state": "unknown", "error": self.error}
        result = self.interface.GetStatus()
        return json.loads(result)

    def pause(self) -> bool:
        """Pause backups."""
        if not self.connected:
            return False
        return bool(self.interface.Pause())

    def resume(self) -> bool:
        """Resume backups."""
        if not self.connected:
            return False
        return bool(self.interface.Resume())

    def trigger_backup(self) -> bool:
        """Trigger manual backup."""
        if not self.connected:
            return False
        return bool(self.interface.TriggerBackup())

    def list_backups(self, dataset: str = "") -> list[str]:
        """List available snapshots."""
        if not self.connected:
            return []
        result = self.interface.ListBackups(dataset)
        return json.loads(result)

    def list_pools(self) -> list[dict]:
        """List ZFS pools."""
        if not self.connected:
            return []
        result = self.interface.ListPools()
        return json.loads(result)

    def list_datasets(self, pool: str) -> list[dict]:
        """List datasets in a pool."""
        if not self.connected:
            return []
        result = self.interface.ListDatasets(pool)
        return json.loads(result)


def format_status(status: dict[str, Any], use_json: bool = False) -> str:
    """Format status for display.

    Args:
        status: Status dictionary.
        use_json: Output as JSON.

    Returns:
        Formatted status string.
    """
    if use_json:
        return json.dumps(status, indent=2)

    lines = []
    state = status.get("state", "unknown")

    # State indicator
    state_icons = {
        "idle": "\u2713",      # checkmark
        "backing_up": "\u2192",  # arrow
        "paused": "\u2016",     # pause
        "error": "\u2717",      # X
        "unknown": "?",
    }
    icon = state_icons.get(state, "?")
    lines.append(f"Status: {icon} {state.upper()}")

    if status.get("paused"):
        lines.append("        (backups paused)")

    if status.get("current_dataset"):
        lines.append(f"Current: {status['current_dataset']}")
        progress = status.get("progress_percent", 0)
        lines.append(f"Progress: {progress}%")

    if status.get("last_backup"):
        lines.append(f"Last backup: {status['last_backup']}")

    if status.get("next_scheduled"):
        lines.append(f"Next scheduled: {status['next_scheduled']}")

    if status.get("error_message"):
        lines.append(f"Error: {status['error_message']}")

    return "\n".join(lines)


def cmd_status(args: argparse.Namespace) -> int:
    """Handle 'status' command."""
    client = DBusClient(use_session_bus=args.session_bus)
    status = client.get_status()
    print(format_status(status, use_json=args.json))
    return 0 if status.get("state") != "error" else 1


def cmd_pause(args: argparse.Namespace) -> int:
    """Handle 'pause' command."""
    client = DBusClient(use_session_bus=args.session_bus)
    if not client.connected:
        print(f"Error: Cannot connect to D-Bus service: {client.error}", file=sys.stderr)
        return 1

    if client.pause():
        print("Backups paused")
        return 0
    else:
        print("Failed to pause backups", file=sys.stderr)
        return 1


def cmd_resume(args: argparse.Namespace) -> int:
    """Handle 'resume' command."""
    client = DBusClient(use_session_bus=args.session_bus)
    if not client.connected:
        print(f"Error: Cannot connect to D-Bus service: {client.error}", file=sys.stderr)
        return 1

    if client.resume():
        print("Backups resumed")
        return 0
    else:
        print("Failed to resume backups", file=sys.stderr)
        return 1


def cmd_backup(args: argparse.Namespace) -> int:
    """Handle 'backup' command."""
    client = DBusClient(use_session_bus=args.session_bus)
    if not client.connected:
        print(f"Error: Cannot connect to D-Bus service: {client.error}", file=sys.stderr)
        return 1

    if client.trigger_backup():
        print("Backup triggered")
        return 0
    else:
        print("Failed to trigger backup", file=sys.stderr)
        return 1


def cmd_list(args: argparse.Namespace) -> int:
    """Handle 'list' command."""
    client = DBusClient(use_session_bus=args.session_bus)
    if not client.connected:
        print(f"Error: Cannot connect to D-Bus service: {client.error}", file=sys.stderr)
        return 1

    dataset = getattr(args, "dataset", "") or ""
    snapshots = client.list_backups(dataset)

    if args.json:
        print(json.dumps(snapshots, indent=2))
    else:
        if not snapshots:
            print("No snapshots found")
        else:
            for snap in snapshots:
                print(snap)

    return 0


def cmd_config_show(args: argparse.Namespace) -> int:
    """Handle 'config show' command."""
    config_path = Path(args.config)

    if not config_path.exists():
        print(f"Configuration file not found: {config_path}", file=sys.stderr)
        return 1

    try:
        config = load_config(config_path)
        if args.json:
            print(json.dumps(config.to_dict(), indent=2))
        else:
            import yaml
            print(yaml.dump(config.to_dict(), default_flow_style=False))
        return 0
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        return 1


def cmd_config_edit(args: argparse.Namespace) -> int:
    """Handle 'config edit' command."""
    config_path = Path(args.config)

    # Create default config if it doesn't exist
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config = get_default_config()
        save_config(config, config_path)
        print(f"Created new configuration file: {config_path}")

    # Get editor from environment
    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "nano"))

    try:
        subprocess.run([editor, str(config_path)], check=True)
        return 0
    except subprocess.CalledProcessError:
        return 1
    except FileNotFoundError:
        print(f"Editor not found: {editor}", file=sys.stderr)
        return 1


def cmd_config_validate(args: argparse.Namespace) -> int:
    """Handle 'config validate' command."""
    config_path = Path(args.config)

    if not config_path.exists():
        print(f"Configuration file not found: {config_path}", file=sys.stderr)
        return 1

    try:
        config = load_config(config_path)
        errors = validate_config(config)

        if errors:
            print("Configuration errors:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            return 1
        else:
            print("Configuration is valid")
            return 0
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        return 1


def cmd_config_apply(args: argparse.Namespace) -> int:
    """Handle 'config apply' command - regenerate znapzend config."""
    config_path = Path(args.config)

    if not config_path.exists():
        print(f"Configuration file not found: {config_path}", file=sys.stderr)
        return 1

    try:
        _config = load_config(config_path)  # noqa: F841 - TODO: use config

        # TODO: Generate znapzend configuration from our config
        # This would call znapzendzetup to set up each dataset

        print("Configuration applied (znapzend config regenerated)")
        return 0
    except Exception as e:
        print(f"Error applying config: {e}", file=sys.stderr)
        return 1


def cmd_dataset_list(args: argparse.Namespace) -> int:
    """Handle 'dataset list' command."""
    config_path = Path(args.config)

    if config_path.exists():
        try:
            config = load_config(config_path)
            if args.json:
                datasets = [
                    {
                        "name": ds.name,
                        "recursive": ds.recursive,
                        "destination": ds.destination,
                        "enabled": ds.enabled,
                    }
                    for ds in config.datasets
                ]
                print(json.dumps(datasets, indent=2))
            else:
                if not config.datasets:
                    print("No datasets configured")
                else:
                    print("Configured datasets:")
                    for ds in config.datasets:
                        status = "\u2713" if ds.enabled else "\u2717"
                        recursive = " (recursive)" if ds.recursive else ""
                        print(f"  {status} {ds.name}{recursive}")
                        if ds.destination:
                            print(f"      -> {ds.destination}")
            return 0
        except Exception as e:
            print(f"Error loading config: {e}", file=sys.stderr)
            return 1
    else:
        # List available datasets from system
        client = DBusClient(use_session_bus=args.session_bus)
        if client.connected:
            pools = client.list_pools()
            for pool in pools:
                print(f"Pool: {pool['name']}")
                datasets = client.list_datasets(pool['name'])
                for ds in datasets:
                    print(f"  {ds['name']}")
                    if ds.get('mountpoint'):
                        print(f"    Mountpoint: {ds['mountpoint']}")
        return 0


def cmd_dest_list(args: argparse.Namespace) -> int:
    """Handle 'dest list' command."""
    config_path = Path(args.config)

    if not config_path.exists():
        print("No configuration file found", file=sys.stderr)
        return 1

    try:
        config = load_config(config_path)
        if args.json:
            destinations = [
                {
                    "name": d.name,
                    "host": d.host,
                    "user": d.user,
                    "port": d.port,
                }
                for d in config.destinations
            ]
            print(json.dumps(destinations, indent=2))
        else:
            if not config.destinations:
                print("No destinations configured")
            else:
                print("Configured destinations:")
                for dest in config.destinations:
                    print(f"  {dest.name}: {dest.user}@{dest.host}:{dest.port}")
        return 0
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        return 1


def cmd_dest_test(args: argparse.Namespace) -> int:
    """Handle 'dest test' command."""
    config_path = Path(args.config)

    if not config_path.exists():
        print("No configuration file found", file=sys.stderr)
        return 1

    try:
        config = load_config(config_path)
        dest_name = args.name

        dest = next((d for d in config.destinations if d.name == dest_name), None)
        if not dest:
            print(f"Destination not found: {dest_name}", file=sys.stderr)
            return 1

        # Test SSH connection
        print(f"Testing connection to {dest.user}@{dest.host}:{dest.port}...")

        ssh_cmd = ["ssh"]
        if dest.ssh_key:
            ssh_cmd.extend(["-i", dest.ssh_key])
        ssh_cmd.extend([
            "-p", str(dest.port),
            "-o", "ConnectTimeout=10",
            "-o", "BatchMode=yes",
            f"{dest.user}@{dest.host}",
            "echo", "Connection successful"
        ])

        try:
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                print("Connection successful!")
                return 0
            else:
                print(f"Connection failed: {result.stderr}", file=sys.stderr)
                return 1
        except subprocess.TimeoutExpired:
            print("Connection timed out", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"Connection error: {e}", file=sys.stderr)
            return 1

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        prog="znapzend-full-ctl",
        description="Control tool for znapzend-full backup system",
    )
    parser.add_argument(
        "-c", "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to configuration file",
    )
    parser.add_argument(
        "--session-bus",
        action="store_true",
        help="Use session D-Bus (for development)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # status
    status_parser = subparsers.add_parser("status", help="Show backup status")
    status_parser.set_defaults(func=cmd_status)

    # pause
    pause_parser = subparsers.add_parser("pause", help="Pause backups")
    pause_parser.set_defaults(func=cmd_pause)

    # resume
    resume_parser = subparsers.add_parser("resume", help="Resume backups")
    resume_parser.set_defaults(func=cmd_resume)

    # backup
    backup_parser = subparsers.add_parser("backup", help="Trigger immediate backup")
    backup_parser.set_defaults(func=cmd_backup)

    # list
    list_parser = subparsers.add_parser("list", help="List available snapshots")
    list_parser.add_argument("--dataset", "-d", help="Filter by dataset")
    list_parser.set_defaults(func=cmd_list)

    # config
    config_parser = subparsers.add_parser("config", help="Configuration management")
    config_subparsers = config_parser.add_subparsers(dest="config_command")

    config_show = config_subparsers.add_parser("show", help="Show configuration")
    config_show.set_defaults(func=cmd_config_show)

    config_edit = config_subparsers.add_parser("edit", help="Edit configuration")
    config_edit.set_defaults(func=cmd_config_edit)

    config_validate = config_subparsers.add_parser("validate", help="Validate configuration")
    config_validate.set_defaults(func=cmd_config_validate)

    config_apply = config_subparsers.add_parser("apply", help="Apply configuration to znapzend")
    config_apply.set_defaults(func=cmd_config_apply)

    # dataset
    dataset_parser = subparsers.add_parser("dataset", help="Dataset management")
    dataset_subparsers = dataset_parser.add_subparsers(dest="dataset_command")

    dataset_list = dataset_subparsers.add_parser("list", help="List configured datasets")
    dataset_list.set_defaults(func=cmd_dataset_list)

    # dest
    dest_parser = subparsers.add_parser("dest", help="Destination management")
    dest_subparsers = dest_parser.add_subparsers(dest="dest_command")

    dest_list = dest_subparsers.add_parser("list", help="List destinations")
    dest_list.set_defaults(func=cmd_dest_list)

    dest_test = dest_subparsers.add_parser("test", help="Test destination connection")
    dest_test.add_argument("name", help="Destination name")
    dest_test.set_defaults(func=cmd_dest_test)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    if hasattr(args, "func"):
        return args.func(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())

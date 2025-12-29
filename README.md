# znapzend-full

A comprehensive backup wrapper for [znapzend](https://github.com/oetiker/znapzend) that provides full system backup and restore capabilities.

## Overview

While znapzend excels at ZFS snapshot replication, restoring a complete system from backup requires additional steps: recreating partition layouts, restoring EFI partitions, applying ZFS properties, and fixing boot configuration. **znapzend-full** solves this by:

- Backing up everything needed for a complete system restore
- Providing an interactive restore utility
- Offering a modern UI for monitoring and control
- Supporting both desktop and headless (server/Proxmox) environments

## Features

- **Complete System Backup**
  - EFI partition images
  - GPT partition layouts (binary + human-readable)
  - ZFS pool vdev configuration
  - All ZFS and zpool properties
  - Efficient hash-based change detection

- **Multiple Interfaces**
  - System tray application (KDE/GNOME/others)
  - Command-line tool for headless systems
  - Interactive TUI for system restore

- **Smart Integration**
  - D-Bus service for real-time status
  - Polkit for secure privilege escalation
  - Systemd service management

## Quick Start

### Installation

**Debian/Ubuntu:**
```bash
sudo dpkg -i znapzend-full_0.1.0-1_all.deb
```

**RHEL/Fedora:**
```bash
sudo rpm -i znapzend-full-0.1.0-1.noarch.rpm
```

**From source:**
```bash
pip install .
```

### Basic Configuration

1. Copy the example configuration:
   ```bash
   sudo cp /usr/share/doc/znapzend-full/config.yaml.example \
           /etc/znapzend-full/config.yaml
   ```

2. Edit the configuration:
   ```bash
   sudo znapzend-full-ctl config edit
   ```

3. Enable and start the service:
   ```bash
   sudo systemctl enable --now znapzend-full
   ```

### Using the CLI (Headless Systems)

```bash
# Check backup status
znapzend-full-ctl status

# Pause backups (e.g., during maintenance)
znapzend-full-ctl pause

# Resume backups
znapzend-full-ctl resume

# List available snapshots
znapzend-full-ctl list

# Trigger immediate backup
znapzend-full-ctl backup
```

### Using the Tray Application (Desktop)

Launch the tray application:
```bash
znapzend-full-tray
```

Or add it to your desktop autostart.

## Documentation

- **[User Guide](docs/usage/README.md)** - Installation, configuration, and daily use
- **[Design Documentation](docs/design/README.md)** - Architecture and development guide

## Requirements

- Linux with ZFS (zfsutils-linux)
- znapzend
- Python 3.9+
- sgdisk (gdisk package)
- SSH client (for remote backups)

**Optional (for GUI):**
- PyQt6
- D-Bus

## License

GPL-3.0-or-later

## Contributing

Contributions are welcome! Please read the [design documentation](docs/design/README.md) to understand the architecture before submitting changes.

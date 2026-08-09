# Installation

## Prerequisites

Before installing znapzend-full, ensure you have:

- **Linux** with a supported distribution (Debian/Ubuntu, RHEL/Fedora, or similar)
- **ZFS** installed and configured (`zfsutils-linux` package)
- **znapzend** installed and working
- **Python 3.9** or later
- **Root access** for installation and service management

### Verify Prerequisites

```bash
# Check ZFS is installed
zfs version

# Check znapzend is installed
znapzend --version

# Check Python version
python3 --version
```

## Installation Methods

### Debian/Ubuntu (Recommended)

Download the latest `.deb` package and install:

```bash
sudo apt update
sudo apt install ./znapzend-full_0.1.0-1_all.deb
```

This will automatically:
- Install all dependencies
- Set up systemd services
- Configure D-Bus and Polkit
- Create the configuration directory

### RHEL/Fedora/CentOS

Download the latest `.rpm` package and install:

```bash
sudo dnf install ./znapzend-full-0.1.0-1.noarch.rpm
```

### From Source (Development)

For development or unsupported distributions:

```bash
# Clone the repository
git clone https://github.com/yourusername/znapzend-full.git
cd znapzend-full

# Create virtual environment (optional but recommended)
python3 -m venv venv
source venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Install system files manually
sudo cp bin/znapzend-full-* /usr/local/bin/
sudo cp systemd/*.service /etc/systemd/system/
sudo cp dbus/*.conf /etc/dbus-1/system.d/
sudo cp polkit/*.policy /usr/share/polkit-1/actions/

# Reload systemd
sudo systemctl daemon-reload
```

## Post-Installation Setup

### 1. Create Configuration

If a configuration file wasn't created automatically:

```bash
sudo mkdir -p /etc/znapzend-full
sudo cp /usr/share/doc/znapzend-full/config.yaml.example \
        /etc/znapzend-full/config.yaml
sudo chmod 640 /etc/znapzend-full/config.yaml
```

### 2. Edit Configuration

See [Configuration](configuration.md) for detailed options:

```bash
sudo znapzend-full-ctl config edit
```

### 3. Create Metadata Dataset

The metadata dataset stores EFI images, GPT backups, and ZFS properties:

```bash
# This is done automatically on first run, but you can create it manually:
sudo zfs create rpool/znapzend-full-meta
```

### 4. Start Services

```bash
# Enable and start the D-Bus service
sudo systemctl enable --now znapzend-full-dbus

# Enable and start the main backup service
sudo systemctl enable --now znapzend-full
```

### 5. Verify Installation

```bash
# Check service status
sudo systemctl status znapzend-full
sudo systemctl status znapzend-full-dbus

# Check backup status via CLI
znapzend-full-ctl status
```

## GUI Installation (Optional)

For desktop systems, install the GUI package:

**Debian/Ubuntu:**
```bash
sudo apt install ./znapzend-full-gui_0.1.0-1_all.deb
```

**From source:**
```bash
pip install PyQt6
```

### Autostart Tray Application

**KDE Plasma:**
1. System Settings → Startup and Shutdown → Autostart
2. Add → Add Application
3. Enter: `znapzend-full-tray`

**GNOME:**
```bash
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/znapzend-full-tray.desktop << EOF
[Desktop Entry]
Type=Application
Name=ZnapZend Full Backup
Exec=znapzend-full-tray
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF
```

## Upgrading

### Package Upgrade

**Debian/Ubuntu:**
```bash
sudo apt install ./znapzend-full_NEW_VERSION_all.deb
```

**RHEL/Fedora:**
```bash
sudo dnf upgrade ./znapzend-full-NEW_VERSION.noarch.rpm
```

### Configuration Migration

Configuration files are preserved during upgrades. Check the changelog for any new options you may want to add.

## Uninstallation

### Stop Services

```bash
sudo systemctl stop znapzend-full znapzend-full-dbus
sudo systemctl disable znapzend-full znapzend-full-dbus
```

### Remove Package

**Debian/Ubuntu:**
```bash
sudo apt remove znapzend-full
# To also remove configuration:
sudo apt purge znapzend-full
```

**RHEL/Fedora:**
```bash
sudo dnf remove znapzend-full
```

### Manual Cleanup (Optional)

```bash
# Remove metadata dataset (WARNING: deletes backup metadata!)
# sudo zfs destroy rpool/znapzend-full-meta

# Remove logs
sudo rm -rf /var/log/znapzend-full
```

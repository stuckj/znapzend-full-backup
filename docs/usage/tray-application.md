# Tray Application

The znapzend-full tray application provides a graphical interface for monitoring and controlling backups on desktop systems.

## Features

- Real-time backup status in system tray
- Pause/resume backups
- Trigger manual backups
- Configuration dialog
- Works with KDE, GNOME, XFCE, and other desktop environments

## Launching

### Command Line

```bash
znapzend-full-tray
```

With verbose logging:
```bash
znapzend-full-tray --verbose
```

### Autostart

#### KDE Plasma

1. Open **System Settings**
2. Navigate to **Startup and Shutdown** → **Autostart**
3. Click **Add** → **Add Application**
4. Enter: `znapzend-full-tray`
5. Click **OK**

#### GNOME

Create a desktop entry:
```bash
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/znapzend-full-tray.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=ZnapZend Full Backup
Comment=Backup status monitor
Exec=znapzend-full-tray
Icon=drive-harddisk
Terminal=false
Categories=System;Utility;
X-GNOME-Autostart-enabled=true
EOF
```

#### XFCE

1. Open **Settings** → **Session and Startup**
2. Go to **Application Autostart** tab
3. Click **Add**
4. Fill in:
   - Name: `ZnapZend Full Backup`
   - Command: `znapzend-full-tray`
5. Click **OK**

## Tray Icon Status

The tray icon color indicates the current backup status:

| Icon Color | Status | Description |
|------------|--------|-------------|
| 🟢 Green | Idle | No backup in progress, system healthy |
| 🔵 Blue | Backing Up | Backup currently running |
| 🟡 Yellow | Paused | Backups are paused |
| 🔴 Red | Error | Last backup failed |
| ⚫ Gray | Unknown | Cannot connect to service |

## Tooltip

Hover over the tray icon to see detailed status:

```
znapzend-full
Idle
Last backup: 2025-12-29T10:30:00
```

During backup:
```
znapzend-full
Backup in progress
Dataset: rpool/home
Progress: 45%
```

## Context Menu

Right-click the tray icon to access the context menu:

```
┌─────────────────────────┐
│ Status: Idle            │  (not clickable)
├─────────────────────────┤
│ Pause Backups           │  or "Resume Backups"
│ Backup Now              │
├─────────────────────────┤
│ View Backup History     │
├─────────────────────────┤
│ Configure...            │
├─────────────────────────┤
│ Quit                    │
└─────────────────────────┘
```

### Menu Items

#### Status
Shows current backup status. This is informational only and cannot be clicked.

#### Pause Backups / Resume Backups
Toggle backup pause state. When paused:
- No new backups will start
- Currently running backups will complete
- The tray icon turns yellow

#### Backup Now
Trigger an immediate backup. This runs the pre-backup script and then znapzend.

Disabled when:
- A backup is already in progress
- Backups are paused

#### View Backup History
Shows information about available snapshots. Currently displays instructions to use the CLI.

#### Configure...
Opens the configuration dialog (see below).

#### Quit
Exit the tray application. This does NOT stop the backup service - backups continue running in the background.

## Configuration Dialog

Click **Configure...** in the context menu to open the configuration dialog.

### ZFS Datasets Tab

![Datasets Tab](images/config-datasets.png)

**Left Panel: Dataset Tree**
- Shows all available ZFS datasets
- Check/uncheck to include in backups
- Expand pools to see child datasets

**Right Panel: Dataset Settings**
- **Recursive backup**: Include all child datasets
- **Destination**: Remote backup location (format: `host:pool/path`)
- **Retention Policy**: How long to keep snapshots
  - Hourly: Number of hourly snapshots
  - Daily: Number of daily snapshots
  - Weekly: Number of weekly snapshots
  - Monthly: Number of monthly snapshots
  - Yearly: Number of yearly snapshots

### Additional Backups Tab

![Additional Backups Tab](images/config-additional.png)

**EFI Partitions**
- Lists detected EFI partitions
- Check partitions to include in backup
- Multiple partitions supported (for mirrored boot)

**GPT Partition Tables**
- Lists disks with GPT partition tables
- Check disks to backup partition layout
- Both binary and human-readable backups are created

### Destinations Tab

![Destinations Tab](images/config-destinations.png)

**Destination List**
- Shows configured remote destinations
- Add/Remove destinations

**Destination Settings**
- **Name**: Friendly name
- **Host**: Hostname or IP
- **User**: SSH username
- **Port**: SSH port
- **SSH Key**: Path to private key

**Test Connection**: Verify SSH connectivity

### Saving Configuration

Click **Save** to save changes. The configuration is validated before saving:
- Invalid settings show warning dialogs
- Valid configuration is saved to `/etc/znapzend-full/config.yaml`

Click **Cancel** to discard changes.

## Notifications

The tray application shows desktop notifications for:
- Backup paused/resumed
- Backup triggered
- Errors

## Troubleshooting

### Tray Icon Not Visible

**KDE Plasma:**
- Right-click the system tray → **Configure System Tray**
- Find "ZnapZend Full Backup" and set to **Always Visible**

**GNOME:**
- Install the [AppIndicator extension](https://extensions.gnome.org/extension/615/appindicator-support/)
- Enable it in GNOME Extensions

**XFCE:**
- Right-click panel → **Panel** → **Add New Items**
- Add **Status Tray Plugin** if not present

### "Cannot connect to service"

The D-Bus service isn't running:
```bash
sudo systemctl status znapzend-full-dbus
sudo systemctl start znapzend-full-dbus
```

### Configuration dialog doesn't save

You need root privileges to save configuration:
- The dialog uses Polkit to request authorization
- A password prompt should appear
- If not, check Polkit configuration:
  ```bash
  ls -la /usr/share/polkit-1/actions/org.znapzend.full.policy
  ```

### High CPU usage

The tray app polls status every 5 seconds. If this causes issues:
1. Check D-Bus service responsiveness
2. Restart the tray application
3. Check system logs for errors

### Application crashes on startup

Check for missing dependencies:
```bash
python3 -c "import PyQt6; print('PyQt6 OK')"
python3 -c "import dbus; print('dbus OK')"
```

Run with verbose logging to see errors:
```bash
znapzend-full-tray --verbose
```

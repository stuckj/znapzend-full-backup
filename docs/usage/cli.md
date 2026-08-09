# Command-Line Interface

The `znapzend-full-ctl` command provides full control over znapzend-full from the command line. This is essential for headless systems like Proxmox servers.

## Synopsis

```
znapzend-full-ctl [-c CONFIG] [--session-bus] [--json] COMMAND [OPTIONS]
```

## Global Options

| Option | Description |
|--------|-------------|
| `-c, --config PATH` | Path to configuration file (default: `/etc/znapzend-full/config.yaml`) |
| `--session-bus` | Use session D-Bus instead of system bus (for development) |
| `--json` | Output in JSON format (useful for scripting) |

## Commands

### `status`

Show current backup status.

```bash
znapzend-full-ctl status
```

**Output:**
```
Status: ✓ IDLE
Last backup: 2025-12-29T10:30:00
```

**JSON output:**
```bash
znapzend-full-ctl status --json
```
```json
{
  "state": "idle",
  "current_dataset": "",
  "progress_percent": 0,
  "last_backup": "2025-12-29T10:30:00",
  "next_scheduled": "2025-12-29T11:00:00",
  "error_message": null,
  "paused": false
}
```

**Status states:**
| State | Icon | Description |
|-------|------|-------------|
| `idle` | ✓ | No backup in progress |
| `backing_up` | → | Backup currently running |
| `paused` | ‖ | Backups are paused |
| `error` | ✗ | Last backup failed |
| `unknown` | ? | Cannot connect to service |

### `pause`

Pause all backups. Useful during maintenance or when you need maximum system performance.

```bash
znapzend-full-ctl pause
```

**Output:**
```
Backups paused
```

**Note:** Pausing will not interrupt a backup that's already in progress. The pause takes effect before the next scheduled backup.

### `resume`

Resume paused backups.

```bash
znapzend-full-ctl resume
```

**Output:**
```
Backups resumed
```

### `backup`

Trigger an immediate backup.

```bash
znapzend-full-ctl backup
```

**Output:**
```
Backup triggered
```

**Note:** This triggers the pre-backup script and then znapzend. The backup runs in the background.

### `list`

List available snapshots/backups.

```bash
# List all snapshots
znapzend-full-ctl list

# Filter by dataset
znapzend-full-ctl list --dataset rpool/ROOT
znapzend-full-ctl list -d rpool/home
```

**Output:**
```
rpool/ROOT@znapzend-auto-2025-12-29T10:00:00
rpool/ROOT@znapzend-auto-2025-12-29T09:00:00
rpool/ROOT@znapzend-auto-2025-12-29T08:00:00
...
```

**JSON output:**
```bash
znapzend-full-ctl list --json
```
```json
[
  "rpool/ROOT@znapzend-auto-2025-12-29T10:00:00",
  "rpool/ROOT@znapzend-auto-2025-12-29T09:00:00"
]
```

### `config`

Configuration management commands.

#### `config show`

Display current configuration.

```bash
znapzend-full-ctl config show
```

**JSON output:**
```bash
znapzend-full-ctl config show --json
```

#### `config edit`

Open configuration in your default editor (`$EDITOR`).

```bash
sudo znapzend-full-ctl config edit
```

This opens `/etc/znapzend-full/config.yaml` in your editor. If the file doesn't exist, a default configuration is created first.

#### `config validate`

Validate the configuration file.

```bash
sudo znapzend-full-ctl config validate
```

**Output (valid):**
```
Configuration is valid
```

**Output (invalid):**
```
Configuration errors:
  - Dataset rpool/ROOT: destination should be in format 'host:path'
  - Destination backup-server: host is required
```

#### `config apply`

Apply configuration changes to znapzend.

```bash
sudo znapzend-full-ctl config apply
```

This regenerates the znapzend configuration based on your znapzend-full config.

### `dataset`

Dataset management commands.

#### `dataset list`

List configured datasets.

```bash
znapzend-full-ctl dataset list
```

**Output:**
```
Configured datasets:
  ✓ rpool/ROOT (recursive)
      -> backup-server:tank/backups/myhost/ROOT
  ✓ rpool/home (recursive)
      -> backup-server:tank/backups/myhost/home
```

If no configuration exists, lists available system datasets instead.

### `dest`

Destination management commands.

#### `dest list`

List configured destinations.

```bash
znapzend-full-ctl dest list
```

**Output:**
```
Configured destinations:
  backup-server: root@backup.local:22
  offsite: backup@offsite.example.com:2222
```

#### `dest test`

Test SSH connection to a destination.

```bash
znapzend-full-ctl dest test backup-server
```

**Output (success):**
```
Testing connection to root@backup.local:22...
Connection successful!
```

**Output (failure):**
```
Testing connection to root@backup.local:22...
Connection failed: Permission denied (publickey)
```

## Exit Codes

| Code | Description |
|------|-------------|
| 0 | Success |
| 1 | Error (connection failed, validation error, etc.) |

## Examples

### Scripting

Check if backups are paused:
```bash
if znapzend-full-ctl status --json | jq -e '.paused' > /dev/null; then
    echo "Backups are paused"
fi
```

Get last backup time:
```bash
znapzend-full-ctl status --json | jq -r '.last_backup'
```

Monitor backup progress:
```bash
watch -n 5 'znapzend-full-ctl status'
```

### Maintenance Window

Pause backups during a maintenance window:
```bash
#!/bin/bash
znapzend-full-ctl pause
echo "Performing maintenance..."
# ... maintenance tasks ...
znapzend-full-ctl resume
echo "Maintenance complete, backups resumed"
```

### Cron Integration

Check backup status daily:
```cron
0 9 * * * /usr/bin/znapzend-full-ctl status --json | /usr/local/bin/check-backup-status.sh
```

### Pre-shutdown Backup

Trigger backup before shutdown:
```bash
#!/bin/bash
# /usr/local/bin/backup-and-shutdown.sh
znapzend-full-ctl backup
sleep 60  # Wait for backup to start
while znapzend-full-ctl status --json | jq -e '.state == "backing_up"' > /dev/null; do
    sleep 30
done
shutdown -h now
```

## Troubleshooting

### "Cannot connect to D-Bus service"

The D-Bus service isn't running:
```bash
sudo systemctl status znapzend-full-dbus
sudo systemctl start znapzend-full-dbus
```

### "Permission denied"

Most commands require root privileges:
```bash
sudo znapzend-full-ctl status
```

Or ensure the D-Bus policy is installed:
```bash
ls -la /etc/dbus-1/system.d/org.znapzend.Full.conf
```

### Commands hang

Check if the D-Bus service is responsive:
```bash
sudo systemctl restart znapzend-full-dbus
```

Check logs:
```bash
journalctl -u znapzend-full-dbus -f
```

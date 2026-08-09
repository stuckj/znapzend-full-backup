# D-Bus Interface

This document specifies the D-Bus interface for znapzend-full.

## Overview

| Property | Value |
|----------|-------|
| Bus | System bus |
| Bus name | `org.znapzend.Full` |
| Object path | `/org/znapzend/Full` |
| Interface | `org.znapzend.Full` |

## Methods

### GetStatus

Get current backup status.

**Signature:** `() → s`

**Returns:** JSON string with status object

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

**State values:**
- `idle` - No backup in progress
- `backing_up` - Backup currently running
- `paused` - Backups are paused
- `error` - Last backup failed

**Example (Python):**
```python
import dbus
import json

bus = dbus.SystemBus()
proxy = bus.get_object('org.znapzend.Full', '/org/znapzend/Full')
iface = dbus.Interface(proxy, 'org.znapzend.Full')

status = json.loads(iface.GetStatus())
print(f"State: {status['state']}")
```

**Example (CLI):**
```bash
dbus-send --system --print-reply --dest=org.znapzend.Full \
    /org/znapzend/Full org.znapzend.Full.GetStatus
```

### Pause

Pause backups.

**Signature:** `() → b`

**Returns:** `true` if successfully paused, `false` if cannot pause (e.g., backup in progress)

**Example:**
```python
success = iface.Pause()
```

### Resume

Resume paused backups.

**Signature:** `() → b`

**Returns:** `true` if successfully resumed

**Example:**
```python
success = iface.Resume()
```

### IsPaused

Check if backups are paused.

**Signature:** `() → b`

**Returns:** `true` if paused

### GetConfig

Get current configuration.

**Signature:** `() → s`

**Returns:** JSON string with configuration

### SetConfig

Update configuration.

**Signature:** `(s) → b`

**Parameters:**
- `config_json` (string): JSON configuration

**Returns:** `true` if saved successfully

### ListBackups

List available snapshots.

**Signature:** `(s) → s`

**Parameters:**
- `dataset` (string): Dataset name (empty for all)

**Returns:** JSON array of snapshot names

```json
[
  "rpool/ROOT@znapzend-auto-2025-12-29T10:00:00",
  "rpool/ROOT@znapzend-auto-2025-12-29T09:00:00"
]
```

### TriggerBackup

Manually trigger a backup.

**Signature:** `() → b`

**Returns:** `true` if backup was triggered

### ListPools

List ZFS pools.

**Signature:** `() → s`

**Returns:** JSON array of pool info

```json
[
  {
    "name": "rpool",
    "size": 500107862016,
    "allocated": 125026965504,
    "free": 375080896512,
    "health": "ONLINE"
  }
]
```

### ListDatasets

List datasets in a pool.

**Signature:** `(s) → s`

**Parameters:**
- `pool` (string): Pool name

**Returns:** JSON array of dataset info

```json
[
  {
    "name": "rpool/ROOT",
    "mountpoint": "/",
    "used": 10737418240,
    "available": 375080896512,
    "type": "filesystem"
  }
]
```

### NotifyBackupStarting

Called by pre-backup script to notify backup is starting.

**Signature:** `()`

**Note:** Internal use only. Updates state to `backing_up`.

### NotifyBackupCompleted

Called by post-backup script to notify backup completed.

**Signature:** `(b)`

**Parameters:**
- `success` (boolean): Whether backup succeeded

**Note:** Internal use only. Updates state to `idle` or `error`.

### NotifyProgress

Update backup progress.

**Signature:** `(si)`

**Parameters:**
- `dataset` (string): Current dataset
- `percent` (int32): Progress percentage (0-100)

## Signals

### StatusChanged

Emitted when status changes.

**Signature:** `(s)`

**Parameters:**
- `status_json` (string): JSON status (same as GetStatus)

**Example (Python):**
```python
def on_status_changed(status_json):
    status = json.loads(status_json)
    print(f"New state: {status['state']}")

bus.add_signal_receiver(
    on_status_changed,
    signal_name="StatusChanged",
    dbus_interface="org.znapzend.Full",
    bus_name="org.znapzend.Full",
)
```

### BackupStarted

Emitted when a backup starts.

**Signature:** `(s)`

**Parameters:**
- `dataset` (string): Dataset being backed up (may be empty)

### BackupCompleted

Emitted when a backup completes.

**Signature:** `(sb)`

**Parameters:**
- `dataset` (string): Dataset that was backed up
- `success` (boolean): Whether backup succeeded

## D-Bus Policy

File: `/etc/dbus-1/system.d/org.znapzend.Full.conf`

```xml
<!DOCTYPE busconfig PUBLIC
 "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <!-- Only root can own the service -->
  <policy user="root">
    <allow own="org.znapzend.Full"/>
    <allow send_destination="org.znapzend.Full"/>
    <allow receive_sender="org.znapzend.Full"/>
  </policy>

  <!-- Allow any user to call methods and receive signals -->
  <policy context="default">
    <allow send_destination="org.znapzend.Full"/>
    <allow receive_sender="org.znapzend.Full"/>
  </policy>
</busconfig>
```

## Polkit Integration

Authorization is handled by Polkit for privileged operations.

File: `/usr/share/polkit-1/actions/org.znapzend.full.policy`

| Action ID | Description | Default |
|-----------|-------------|---------|
| `org.znapzend.full.status` | View status | Allow all |
| `org.znapzend.full.control` | Pause/resume | Admin auth |
| `org.znapzend.full.backup` | Trigger backup | Admin auth |
| `org.znapzend.full.configure` | Modify config | Admin auth |

## Introspection

The service supports D-Bus introspection:

```bash
dbus-send --system --print-reply --dest=org.znapzend.Full \
    /org/znapzend/Full org.freedesktop.DBus.Introspectable.Introspect
```

## Error Handling

Methods return `false` or empty results on error. Detailed errors are logged to the journal.

Check service logs:
```bash
journalctl -u znapzend-full-dbus -f
```

## Testing

### Session Bus (Development)

For development without root:

```python
# Service
python -m znapzend_full.dbus_service --session-bus

# Client
bus = dbus.SessionBus()
```

### D-Bus Monitor

Monitor D-Bus traffic:
```bash
dbus-monitor --system "interface='org.znapzend.Full'"
```

### busctl

Alternative interface using busctl:
```bash
busctl --system call org.znapzend.Full /org/znapzend/Full \
    org.znapzend.Full GetStatus
```

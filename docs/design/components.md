# Component Design

This document details the design of each major component in znapzend-full.

## Pre-Backup Script

**File:** `bin/znapzend-full-pre-backup`
**Language:** Bash
**Runs as:** root (via systemd)

### Purpose

Capture non-ZFS system data before znapzend runs its backup.

### Flow

```
Start
  │
  ├─► Check if paused (D-Bus query)
  │     └─► Exit if paused
  │
  ├─► Notify D-Bus: backup starting
  │
  ├─► Parse configuration
  │
  ├─► Ensure metadata dataset exists
  │
  ├─► For each EFI partition:
  │     ├─► dd to temp file
  │     ├─► Compute SHA256
  │     ├─► Compare with stored hash
  │     └─► Replace if different
  │
  ├─► For each GPT disk:
  │     ├─► sgdisk --backup (binary)
  │     ├─► sgdisk --print (text)
  │     └─► Update with hash check
  │
  ├─► For each zpool:
  │     ├─► zpool status (vdev layout)
  │     ├─► zpool get all (properties)
  │     └─► Update with hash check
  │
  ├─► For each ZFS dataset:
  │     ├─► zfs get all -r (all properties)
  │     └─► Update with hash check
  │
  └─► Log completion
```

### Error Handling

- Errors are logged but don't stop the backup
- Partial metadata backup is better than none
- Each backup type is independent

### Configuration Parsing

Uses Python for YAML parsing (called via subprocess):

```bash
eval "$(python3 -c "
import yaml
with open('$CONFIG_FILE') as f:
    config = yaml.safe_load(f)
# Output shell variables
print('METADATA_DATASET=\"{}\"'.format(config['metadata_dataset']))
# ...
")"
```

## Post-Backup Script

**File:** `bin/znapzend-full-post-backup`
**Language:** Bash
**Runs as:** root (via systemd)

### Purpose

Notify completion and perform cleanup after znapzend finishes.

### Flow

```
Start
  │
  ├─► Get exit code (from argument or environment)
  │
  ├─► Notify D-Bus: backup completed
  │     └─► Include success/failure status
  │
  └─► Log completion
```

### Exit Code Handling

The script receives znapzend's exit code and reports it to the D-Bus service.

## D-Bus Service

**File:** `src/znapzend_full/dbus_service.py`
**Language:** Python
**Runs as:** root (systemd service)

### Purpose

Central coordinator providing:
- Status tracking
- Pause/resume control
- Configuration access
- Real-time notifications

### Interface Definition

**Bus Name:** `org.znapzend.Full`
**Object Path:** `/org/znapzend/Full`

#### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `GetStatus` | `() → s` | Returns JSON status |
| `Pause` | `() → b` | Pause backups |
| `Resume` | `() → b` | Resume backups |
| `IsPaused` | `() → b` | Check pause state |
| `GetConfig` | `() → s` | Get config as JSON |
| `SetConfig` | `(s) → b` | Set config from JSON |
| `ListBackups` | `(s) → s` | List snapshots |
| `TriggerBackup` | `() → b` | Start backup |
| `ListPools` | `() → s` | List ZFS pools |
| `ListDatasets` | `(s) → s` | List datasets in pool |
| `NotifyBackupStarting` | `()` | Called by pre-backup |
| `NotifyBackupCompleted` | `(b)` | Called by post-backup |
| `NotifyProgress` | `(si)` | Update progress |

#### Signals

| Signal | Signature | Description |
|--------|-----------|-------------|
| `StatusChanged` | `(s)` | Status JSON changed |
| `BackupStarted` | `(s)` | Backup began |
| `BackupCompleted` | `(sb)` | Backup finished |

### State Management

```python
class BackupState:
    IDLE = "idle"
    BACKING_UP = "backing_up"
    PAUSED = "paused"
    ERROR = "error"
```

State transitions:
```
                 ┌───────────────┐
                 │     IDLE      │◄─────────────────┐
                 └───────┬───────┘                  │
                         │ NotifyBackupStarting     │
                         ▼                          │
                 ┌───────────────┐                  │
      ┌─────────►│  BACKING_UP   │                  │
      │          └───────┬───────┘                  │
      │                  │ NotifyBackupCompleted    │
      │                  ▼                          │
      │          ┌───────────────┐                  │
      │          │ success=true? ├──── yes ────────►│
      │          └───────┬───────┘                  │
      │                  │ no                       │
      │                  ▼                          │
      │          ┌───────────────┐                  │
      │          │     ERROR     │─── auto-clear ──►│
      │          └───────────────┘                  │
      │                                             │
      │          ┌───────────────┐                  │
      └── Resume │    PAUSED     │◄─── Pause ───────┘
                 └───────────────┘
```

### Thread Safety

State access is protected by a lock:

```python
def GetStatus(self) -> str:
    with self._lock:
        return json.dumps(self._get_status_dict())
```

## CLI Tool

**File:** `src/znapzend_full/cli/ctl.py`
**Language:** Python
**Runs as:** User or root (depending on command)

### Purpose

Command-line interface for:
- Status checking
- Backup control
- Configuration management
- Headless system administration

### Architecture

```
┌───────────────────────────────────────────────────────────┐
│                    znapzend-full-ctl                       │
├───────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐   │
│  │   argparse  │    │ DBusClient  │    │   Output    │   │
│  │   (parser)  │───►│  (client)   │───►│ (formatter) │   │
│  └─────────────┘    └─────────────┘    └─────────────┘   │
└───────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
    Command tree         D-Bus system        JSON/Text
                            bus              output
```

### Command Structure

```
znapzend-full-ctl
├── status          # Show backup status
├── pause           # Pause backups
├── resume          # Resume backups
├── backup          # Trigger backup
├── list            # List snapshots
├── config
│   ├── show        # Display config
│   ├── edit        # Edit in $EDITOR
│   ├── validate    # Check config
│   └── apply       # Apply to znapzend
├── dataset
│   └── list        # List configured datasets
└── dest
    ├── list        # List destinations
    └── test        # Test SSH connection
```

### D-Bus Client

```python
class DBusClient:
    def __init__(self, use_session_bus=False):
        bus = dbus.SessionBus() if use_session_bus else dbus.SystemBus()
        self.proxy = bus.get_object(DBUS_BUS_NAME, DBUS_OBJECT_PATH)
        self.interface = dbus.Interface(self.proxy, DBUS_INTERFACE)
```

## Tray Application

**File:** `ui/znapzend_full/tray.py`
**Language:** Python (PyQt6)
**Runs as:** User

### Purpose

Visual status monitoring and control for desktop users.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     TrayApplication                          │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐     ┌──────────────┐     ┌─────────────┐ │
│  │   TrayIcon   │     │  DBusHandler │     │ ConfigDialog│ │
│  │   (QSystem   │◄───►│   (signals)  │     │   (modal)   │ │
│  │   TrayIcon)  │     └──────────────┘     └─────────────┘ │
│  └──────────────┘              │                           │
│         │                      │                           │
│         ▼                      ▼                           │
│  ┌──────────────┐     ┌──────────────┐                    │
│  │  Context     │     │    D-Bus     │                    │
│  │   Menu       │     │ System Bus   │                    │
│  └──────────────┘     └──────────────┘                    │
└─────────────────────────────────────────────────────────────┘
```

### Icon States

Icons are generated programmatically as colored circles:

```python
def create_circle_icon(color: QColor) -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setBrush(color)
    painter.drawEllipse(4, 4, 56, 56)
    return QIcon(pixmap)
```

### D-Bus Signal Handling

```python
class DBusHandler(QObject):
    status_changed = pyqtSignal(dict)

    def __init__(self):
        self.bus.add_signal_receiver(
            self._on_status_changed,
            signal_name="StatusChanged",
            dbus_interface=DBUS_INTERFACE,
        )

    def _on_status_changed(self, status_json):
        status = json.loads(status_json)
        self.status_changed.emit(status)  # Qt signal
```

### Polling Fallback

If D-Bus signals aren't delivered reliably, the app polls every 5 seconds:

```python
self.poll_timer = QTimer(self)
self.poll_timer.timeout.connect(self._poll_status)
self.poll_timer.start(5000)
```

## Configuration Dialog

**File:** `ui/znapzend_full/config_dialog.py`
**Language:** Python (PyQt6)
**Runs as:** User (Polkit for saving)

### Purpose

GUI for configuring backup settings.

### Tab Structure

```
┌─────────────────────────────────────────────────────────────┐
│  ┌─────────────┬─────────────────┬──────────────┐          │
│  │ ZFS Datasets│ Additional      │ Destinations │          │
│  │             │ Backups         │              │          │
├──┴─────────────┴─────────────────┴──────────────┴──────────┤
│                                                             │
│  [Tab content area]                                         │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                              [Save]  [Cancel]               │
└─────────────────────────────────────────────────────────────┘
```

### Dataset Tab Design

Split view with tree and details:

```
┌────────────────────────┬──────────────────────────────────┐
│ Available Datasets:    │ Dataset Settings:                │
│ ┌────────────────────┐ │ ┌──────────────────────────────┐ │
│ │ □ rpool            │ │ │ rpool/ROOT                   │ │
│ │   ☑ ROOT           │ │ ├──────────────────────────────┤ │
│ │   ☑ home           │ │ │ ☑ Recursive backup           │ │
│ │   □ var/cache      │ │ │                              │ │
│ │                    │ │ │ Destination:                 │ │
│ │ □ datapool         │ │ │ [backup:tank/backups/ROOT  ] │ │
│ │   □ media          │ │ │                              │ │
│ └────────────────────┘ │ │ Retention:                   │ │
│                        │ │   Hourly:  [24]              │ │
│ [Refresh]              │ │   Daily:   [7 ]              │ │
│                        │ │   Weekly:  [4 ]              │ │
│                        │ │   Monthly: [12]              │ │
│                        │ └──────────────────────────────┘ │
└────────────────────────┴──────────────────────────────────┘
```

## Restore TUI

**File:** `src/znapzend_full/restore/interactive.py`
**Language:** Python (Textual)
**Runs as:** root

### Purpose

Interactive terminal interface for system recovery.

### Screen Flow

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│   Welcome   │────►│   Snapshot   │────►│  Destination  │
│   (SSH)     │     │   Select     │     │    Select     │
└─────────────┘     └──────────────┘     └───────┬───────┘
                                                  │
┌─────────────┐     ┌──────────────┐              │
│  Complete   │◄────│   Progress   │◄─────────────┘
│             │     │              │     Confirm
└─────────────┘     └──────────────┘
```

### Textual App Structure

```python
class RestoreApp(App):
    def __init__(self):
        self.ssh_client = None
        self.selected_snapshot = None
        self.target_disk = None
        self.restore_options = {}

    def on_mount(self):
        self.push_screen(WelcomeScreen())
```

### SSH Operations

The restore TUI uses `SSHClient` for all remote operations:

```python
class SSHClient:
    def stream_receive(self, snapshot, local_dataset):
        # SSH zfs send | local zfs receive
        send_proc = subprocess.Popen(
            ssh_cmd + [f"zfs send -c {snapshot}"],
            stdout=subprocess.PIPE,
        )
        recv_proc = subprocess.Popen(
            ["zfs", "receive", local_dataset],
            stdin=send_proc.stdout,
        )
```

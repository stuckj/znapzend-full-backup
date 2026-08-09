# Architecture Overview

This document describes the high-level architecture of znapzend-full.

## System Context

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              User's System                                   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         znapzend-full                                 │  │
│  │                                                                       │  │
│  │  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                │  │
│  │  │    Tray     │   │     CLI     │   │   Restore   │                │  │
│  │  │Application  │   │    Tool     │   │    TUI      │                │  │
│  │  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘                │  │
│  │         │                 │                 │                        │  │
│  │         └────────────┬────┴────────────────┘                        │  │
│  │                      │                                               │  │
│  │                      ▼                                               │  │
│  │              ┌───────────────┐                                       │  │
│  │              │  D-Bus Service │◄──────────────────────────────────┐  │  │
│  │              └───────┬───────┘                                    │  │  │
│  │                      │                                            │  │  │
│  │         ┌────────────┴────────────┐                              │  │  │
│  │         ▼                         ▼                              │  │  │
│  │  ┌─────────────┐          ┌─────────────┐                        │  │  │
│  │  │ Pre-Backup  │          │ Post-Backup │                        │  │  │
│  │  │   Script    │          │   Script    │                        │  │  │
│  │  └──────┬──────┘          └──────┬──────┘                        │  │  │
│  │         │                        │                               │  │  │
│  └─────────┼────────────────────────┼───────────────────────────────┘  │
│            │                        │                                   │
│            ▼                        ▼                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                          znapzend                                │   │
│  │                    (existing backup tool)                        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                    │
└────────────────────────────────────┼────────────────────────────────────┘
                                     │
                                     ▼
                        ┌────────────────────────┐
                        │     Backup Server      │
                        │    (remote ZFS pool)   │
                        └────────────────────────┘
```

## Component Architecture

### Layer 1: User Interfaces

Three interfaces for different use cases:

| Interface | Use Case | Technology |
|-----------|----------|------------|
| Tray Application | Desktop users, visual monitoring | PyQt6 |
| CLI Tool | Headless systems, scripting | Python argparse |
| Restore TUI | System recovery, interactive restore | Textual |

All interfaces communicate with the D-Bus service for operations.

### Layer 2: D-Bus Service

Central coordinator running as root:

**Responsibilities:**
- Maintain backup state (idle, running, paused, error)
- Coordinate pause/resume across components
- Emit signals for real-time status updates
- Provide interface for querying configuration and snapshots

**Why D-Bus?**
- Standard Linux IPC mechanism
- Supports signals for push notifications
- Policy-based access control
- Integrates with systemd activation

### Layer 3: Backup Scripts

Bash scripts that run as systemd service hooks:

**Pre-backup (`ExecStartPre`):**
1. Check if paused (via D-Bus)
2. Notify D-Bus service backup is starting
3. Backup EFI partitions
4. Backup GPT layouts
5. Backup zpool status/properties
6. Backup ZFS properties

**Post-backup (`ExecStopPost`):**
1. Notify D-Bus service backup completed
2. Log status

### Layer 4: znapzend Integration

We don't modify znapzend; we wrap it:

```ini
[Service]
ExecStartPre=/usr/lib/znapzend-full/bin/znapzend-full-pre-backup
ExecStart=/usr/bin/znapzend --daemonize=0
ExecStopPost=/usr/lib/znapzend-full/bin/znapzend-full-post-backup
```

## Data Architecture

### Configuration Data

```
/etc/znapzend-full/
└── config.yaml          # Main configuration
```

Configuration is YAML for human readability. See [Configuration System](configuration.md).

### Backup Metadata

```
/rpool/znapzend-full-meta/     # ZFS dataset (included in backups)
├── efi/
│   ├── nvme0n1p1.img          # EFI partition image
│   └── nvme0n1p1.img.sha256   # Hash for change detection
├── gpt/
│   ├── nvme0n1.sgdisk         # Binary GPT backup
│   ├── nvme0n1.txt            # Human-readable GPT
│   └── nvme0n1.sgdisk.sha256
├── zpool/
│   ├── rpool.status           # vdev layout
│   ├── rpool.properties       # Pool properties
│   └── rpool.status.sha256
└── zfs/
    ├── rpool.properties       # All dataset properties
    └── rpool.properties.sha256
```

### Runtime Data

```
/var/log/znapzend-full/
├── pre-backup.log
└── post-backup.log

/run/znapzend-full/            # (potential future use)
```

## Security Architecture

### Privilege Separation

```
┌─────────────────────────────────────────────────────────────┐
│                     User Space                               │
│  ┌─────────────┐                                            │
│  │    Tray     │ ◄─── Runs as user                          │
│  │Application  │                                            │
│  └──────┬──────┘                                            │
│         │ D-Bus (system bus)                                │
│         │ ┌──────────────────────────────────────────────┐  │
│         │ │              Polkit                          │  │
│         │ │  (authentication for privileged operations)  │  │
│         │ └──────────────────────────────────────────────┘  │
├─────────┼───────────────────────────────────────────────────┤
│         ▼           Root Space                              │
│  ┌─────────────┐                                            │
│  │   D-Bus     │ ◄─── Runs as root                          │
│  │   Service   │                                            │
│  └─────────────┘                                            │
│         │                                                   │
│  ┌──────┴──────┐                                            │
│  │   Backup    │ ◄─── Runs as root (systemd service)        │
│  │   Scripts   │                                            │
│  └─────────────┘                                            │
└─────────────────────────────────────────────────────────────┘
```

### D-Bus Policy

```xml
<!-- Only root can own the service -->
<policy user="root">
  <allow own="org.znapzend.Full"/>
</policy>

<!-- Any user can call methods (Polkit handles authorization) -->
<policy context="default">
  <allow send_destination="org.znapzend.Full"/>
</policy>
```

### Polkit Actions

| Action | Description | Default |
|--------|-------------|---------|
| `org.znapzend.full.status` | View status | Allow all |
| `org.znapzend.full.control` | Pause/resume | Admin auth |
| `org.znapzend.full.backup` | Trigger backup | Admin auth |
| `org.znapzend.full.configure` | Modify config | Admin auth |

## Error Handling

### Backup Failures

```
Pre-backup fails → Log error, continue to znapzend
                   (partial backup better than none)

znapzend fails → Post-backup notifies D-Bus
              → Status set to ERROR
              → Service restarts after delay

Post-backup fails → Log error (non-critical)
```

### D-Bus Service Failures

```
D-Bus service crashes → systemd restarts it
                     → Clients reconnect automatically
                     → State recovered from ZFS queries
```

### GUI Failures

```
Tray app crashes → User can restart manually
                → Backups continue (independent service)
```

## Scalability Considerations

### Multiple Pools

Configuration supports multiple pools with separate retention policies.

### Large Datasets

- znapzend handles large dataset transfers
- Hash tracking prevents redundant metadata backups
- Incremental ZFS send for efficient transfers

### Multiple Destinations

znapzend natively supports multiple destinations per dataset.

## Future Considerations

### Potential Enhancements

1. **Web UI** - For remote management
2. **Metrics/Prometheus** - For monitoring integration
3. **Encryption** - For backup-at-rest encryption
4. **Cloud Destinations** - S3-compatible storage

### Extension Points

- Plugin system for additional backup types
- Custom notification handlers
- Alternative IPC mechanisms (REST API)

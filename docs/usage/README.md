# znapzend-full User Guide

This guide covers installation, configuration, and daily use of znapzend-full.

## Table of Contents

1. [Installation](installation.md)
2. [Configuration](configuration.md)
3. [Command-Line Interface](cli.md)
4. [Tray Application](tray-application.md)
5. [Restoring from Backup](restore.md)
6. [Troubleshooting](troubleshooting.md)

## What is znapzend-full?

znapzend-full is a wrapper around znapzend that captures everything needed for a complete system restore:

| Component | What it backs up | Why it matters |
|-----------|------------------|----------------|
| ZFS Snapshots | Your data (via znapzend) | Core backup functionality |
| EFI Partitions | Boot files, kernels | Required for UEFI boot |
| GPT Layout | Partition table | Recreate disk structure |
| ZFS Properties | Mount points, compression, etc. | Restore exact configuration |
| Pool Layout | Mirror/RAIDZ configuration | Recreate pool structure |

## Quick Start

### 1. Install the Package

See [Installation](installation.md) for detailed instructions.

### 2. Configure Your Backups

Edit `/etc/znapzend-full/config.yaml`:

```yaml
datasets:
  - name: rpool/ROOT
    recursive: true
    destination: backup-server:tank/backups/myhost/ROOT

additional_backups:
  efi_partitions:
    - /dev/nvme0n1p1
  gpt_backup:
    - /dev/nvme0n1
  zpool_properties:
    - rpool
  zfs_properties:
    - rpool
```

### 3. Start the Service

```bash
sudo systemctl enable --now znapzend-full
```

### 4. Monitor Your Backups

**Desktop:** Use the tray application
**Headless:** Use `znapzend-full-ctl status`

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                     Your System                              │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │   EFI   │  │  Root   │  │  Home   │  │  Data   │        │
│  │Partition│  │  Pool   │  │ Dataset │  │ Dataset │        │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘        │
│       │            │            │            │              │
│       └────────────┴────────────┴────────────┘              │
│                          │                                   │
│              ┌───────────┴───────────┐                      │
│              │   znapzend-full       │                      │
│              │   pre-backup script   │                      │
│              └───────────┬───────────┘                      │
│                          │                                   │
│    ┌─────────────────────┼─────────────────────┐            │
│    │                     │                     │            │
│    ▼                     ▼                     ▼            │
│ ┌──────┐           ┌──────────┐          ┌──────────┐      │
│ │ EFI  │           │   GPT    │          │   ZFS    │      │
│ │Image │           │  Layout  │          │Properties│      │
│ └──┬───┘           └────┬─────┘          └────┬─────┘      │
│    │                    │                     │             │
│    └────────────────────┼─────────────────────┘             │
│                         │                                   │
│                         ▼                                   │
│              ┌─────────────────────┐                       │
│              │ Metadata Dataset    │                       │
│              │ (rpool/znapzend-    │                       │
│              │  full-meta)         │                       │
│              └──────────┬──────────┘                       │
│                         │                                   │
└─────────────────────────┼───────────────────────────────────┘
                          │
                          ▼
              ┌─────────────────────┐
              │      znapzend       │
              │  (snapshot + send)  │
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │   Backup Server     │
              │   (remote pool)     │
              └─────────────────────┘
```

## Support

If you encounter issues:

1. Check the [Troubleshooting Guide](troubleshooting.md)
2. Review logs: `journalctl -u znapzend-full`
3. File an issue on GitHub

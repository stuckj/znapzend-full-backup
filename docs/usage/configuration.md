# Configuration

znapzend-full uses a YAML configuration file located at `/etc/znapzend-full/config.yaml`.

## Configuration File Structure

```yaml
version: 1

metadata_dataset: rpool/znapzend-full-meta

datasets:
  - name: rpool/ROOT
    recursive: true
    exclude:
      - rpool/ROOT/ubuntu/tmp
    destination: backup-server:tank/backups/myhost/ROOT
    retention:
      hourly: 24
      daily: 7
      weekly: 4
      monthly: 12
    enabled: true

additional_backups:
  efi_partitions:
    - /dev/nvme0n1p1
  gpt_backup:
    - /dev/nvme0n1
  zpool_properties:
    - rpool
  zfs_properties:
    - rpool

destinations:
  - name: backup-server
    host: backup.local
    user: root
    port: 22
    ssh_key: /root/.ssh/id_backup

schedule:
  quiet_hours:
    start: "02:00"
    end: "06:00"
```

## Configuration Options

### `version`

Configuration file version. Currently only `1` is supported.

```yaml
version: 1
```

### `metadata_dataset`

The ZFS dataset where backup metadata (EFI images, GPT layouts, ZFS properties) is stored. This dataset is automatically included in your backups.

```yaml
metadata_dataset: rpool/znapzend-full-meta
```

**Default:** `rpool/znapzend-full-meta`

### `datasets`

List of ZFS datasets to back up. Each dataset can have its own configuration.

#### Dataset Options

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `name` | string | Yes | Full dataset name (e.g., `rpool/ROOT`) |
| `recursive` | boolean | No | Include child datasets (default: `true`) |
| `exclude` | list | No | Child datasets to exclude when recursive |
| `destination` | string | Yes | Remote destination (`host:pool/path`) |
| `retention` | object | No | Snapshot retention policy |
| `enabled` | boolean | No | Enable/disable this dataset (default: `true`) |

#### Retention Policy

Controls how long snapshots are kept:

```yaml
retention:
  hourly: 24    # Keep 24 hourly snapshots
  daily: 7      # Keep 7 daily snapshots
  weekly: 4     # Keep 4 weekly snapshots
  monthly: 12   # Keep 12 monthly snapshots
  yearly: 0     # Keep 0 yearly snapshots (disabled)
```

#### Example: Root Filesystem

```yaml
datasets:
  - name: rpool/ROOT
    recursive: true
    exclude:
      - rpool/ROOT/ubuntu/tmp
      - rpool/ROOT/ubuntu/var/tmp
      - rpool/ROOT/ubuntu/var/cache
      - rpool/ROOT/ubuntu/var/log
    destination: backup-server:tank/backups/myhost/ROOT
    retention:
      hourly: 24
      daily: 7
      weekly: 4
      monthly: 12
    enabled: true
```

#### Example: Home Directories

```yaml
datasets:
  - name: rpool/home
    recursive: true
    destination: backup-server:tank/backups/myhost/home
    retention:
      hourly: 48    # More frequent for user data
      daily: 30
      weekly: 8
      monthly: 24
      yearly: 2
```

### `additional_backups`

Non-ZFS items to back up alongside your datasets.

#### `efi_partitions`

List of EFI partitions to back up. These are saved as raw disk images.

```yaml
additional_backups:
  efi_partitions:
    - /dev/nvme0n1p1
    - /dev/nvme1n1p1    # Second disk in mirror
```

**Finding your EFI partition:**
```bash
# Look for partitions with type "EFI System"
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,PARTTYPE | grep -i efi

# Or check what's mounted at /boot/efi
findmnt /boot/efi
```

#### `gpt_backup`

List of disks to back up GPT partition tables from. Both binary (for restore) and human-readable (for reference) backups are created.

```yaml
additional_backups:
  gpt_backup:
    - /dev/nvme0n1
    - /dev/nvme1n1
```

**Note:** Use whole disk devices (e.g., `/dev/nvme0n1`), not partitions.

#### `zpool_properties`

List of ZFS pools to back up properties for. This captures:
- Pool vdev layout (mirror, raidz, etc.)
- All pool properties

```yaml
additional_backups:
  zpool_properties:
    - rpool
    - datapool
```

#### `zfs_properties`

Datasets/pools to back up ZFS properties for. Properties are captured recursively for all child datasets.

```yaml
additional_backups:
  zfs_properties:
    - rpool        # All datasets under rpool
    - datapool     # All datasets under datapool
```

**Captured properties include:**
- Mount points
- Compression settings
- Quotas and reservations
- ACL settings
- Custom properties

### `destinations`

Remote backup destinations configuration.

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `name` | string | Yes | Friendly name for this destination |
| `host` | string | Yes | Hostname or IP address |
| `user` | string | No | SSH username (default: `root`) |
| `port` | integer | No | SSH port (default: `22`) |
| `ssh_key` | string | No | Path to SSH private key |

```yaml
destinations:
  - name: backup-server
    host: backup.local
    user: root
    port: 22
    ssh_key: /root/.ssh/id_backup

  - name: offsite
    host: offsite.example.com
    user: backup
    port: 2222
    ssh_key: /root/.ssh/id_offsite
```

**Setting up SSH keys:**
```bash
# Generate a dedicated backup key
sudo ssh-keygen -t ed25519 -f /root/.ssh/id_backup -N ""

# Copy to backup server
sudo ssh-copy-id -i /root/.ssh/id_backup root@backup.local

# Test connection
sudo ssh -i /root/.ssh/id_backup root@backup.local echo "Success"
```

### `schedule`

Backup scheduling options.

#### `quiet_hours`

Time period during which backups should not run. Useful if backups impact system performance during certain activities.

```yaml
schedule:
  quiet_hours:
    start: "02:00"
    end: "06:00"
```

Leave empty to disable:
```yaml
schedule:
  quiet_hours:
    start: ""
    end: ""
```

## Managing Configuration

### Edit Configuration

Using the CLI tool (opens in `$EDITOR`):
```bash
sudo znapzend-full-ctl config edit
```

Or edit directly:
```bash
sudo nano /etc/znapzend-full/config.yaml
```

### Validate Configuration

```bash
sudo znapzend-full-ctl config validate
```

### View Current Configuration

```bash
sudo znapzend-full-ctl config show
```

### Apply Configuration

After making changes, apply them to znapzend:
```bash
sudo znapzend-full-ctl config apply
```

## Example Configurations

### Single Disk Laptop

```yaml
version: 1
metadata_dataset: rpool/znapzend-full-meta

datasets:
  - name: rpool/ROOT
    recursive: true
    exclude:
      - rpool/ROOT/ubuntu/tmp
      - rpool/ROOT/ubuntu/var/cache
    destination: nas:tank/backups/laptop/ROOT
    retention:
      hourly: 24
      daily: 7
      weekly: 4
      monthly: 6

  - name: rpool/home
    recursive: true
    destination: nas:tank/backups/laptop/home
    retention:
      hourly: 48
      daily: 30
      weekly: 8
      monthly: 12

additional_backups:
  efi_partitions:
    - /dev/nvme0n1p1
  gpt_backup:
    - /dev/nvme0n1
  zpool_properties:
    - rpool
  zfs_properties:
    - rpool

destinations:
  - name: nas
    host: 192.168.1.100
    user: root
    ssh_key: /root/.ssh/id_backup
```

### Proxmox Server (Mirrored Boot)

```yaml
version: 1
metadata_dataset: rpool/znapzend-full-meta

datasets:
  - name: rpool/ROOT
    recursive: true
    destination: backup:tank/proxmox/node1/ROOT
    retention:
      hourly: 12
      daily: 7
      weekly: 4
      monthly: 12

  - name: rpool/data
    recursive: true
    destination: backup:tank/proxmox/node1/data
    retention:
      hourly: 24
      daily: 14
      weekly: 8
      monthly: 12

additional_backups:
  efi_partitions:
    - /dev/sda1
    - /dev/sdb1      # Mirror
  gpt_backup:
    - /dev/sda
    - /dev/sdb       # Mirror
  zpool_properties:
    - rpool
  zfs_properties:
    - rpool

destinations:
  - name: backup
    host: backup-server.lan
    user: root
    ssh_key: /root/.ssh/id_ed25519
```

### Desktop with Multiple Pools

```yaml
version: 1
metadata_dataset: rpool/znapzend-full-meta

datasets:
  - name: rpool/ROOT
    recursive: true
    exclude:
      - rpool/ROOT/ubuntu/tmp
      - rpool/ROOT/ubuntu/var/cache
      - rpool/ROOT/ubuntu/var/log
    destination: nas:backup/desktop/ROOT
    retention:
      hourly: 24
      daily: 7
      weekly: 4
      monthly: 6

  - name: rpool/home
    recursive: true
    destination: nas:backup/desktop/home
    retention:
      hourly: 48
      daily: 30
      weekly: 12
      monthly: 24
      yearly: 2

  - name: datapool/projects
    recursive: true
    destination: nas:backup/desktop/projects
    retention:
      hourly: 24
      daily: 30
      weekly: 12
      monthly: 24

additional_backups:
  efi_partitions:
    - /dev/nvme0n1p1
  gpt_backup:
    - /dev/nvme0n1
    - /dev/sda       # Data pool disk 1
    - /dev/sdb       # Data pool disk 2
  zpool_properties:
    - rpool
    - datapool
  zfs_properties:
    - rpool
    - datapool

destinations:
  - name: nas
    host: nas.local
    user: backup
    port: 22
    ssh_key: /root/.ssh/id_backup
```

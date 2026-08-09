# Restoring from Backup

This guide covers how to restore a complete system from a znapzend-full backup.

## Overview

A complete system restore involves:

1. Booting from a live environment
2. Recreating partition layout (GPT)
3. Creating ZFS pool(s)
4. Receiving ZFS datasets from backup
5. Restoring EFI partition
6. Applying ZFS properties
7. Fixing boot configuration
8. Rebooting into restored system

znapzend-full provides an interactive restore utility that guides you through this process.

## Prerequisites

### On the Recovery System

You'll need a Linux live environment with:
- ZFS support (`zfsutils-linux`)
- SSH client
- Python 3.9+ (for the restore utility)
- Network connectivity to your backup server

**Recommended live environments:**
- Ubuntu Live USB (install `zfsutils-linux`)
- Proxmox installation ISO
- Any Linux with ZFS support

### On the Backup Server

- SSH access configured
- Backup snapshots available
- Sufficient permissions to read ZFS datasets

### Network Setup

Ensure the recovery system can reach your backup server:
```bash
ping backup-server.local
ssh root@backup-server.local echo "Connection OK"
```

## Interactive Restore

### Starting the Restore Utility

```bash
# If installed
znapzend-full-restore

# Or run directly
python3 -m znapzend_full.restore.interactive
```

### Step 1: Connect to Backup Server

Enter your backup server details:
- **Host**: Backup server hostname or IP
- **User**: SSH username (usually `root`)
- **Port**: SSH port (default: 22)
- **SSH Key**: Path to private key (optional)

Click **Connect** to test and establish connection.

### Step 2: Select Backup Snapshot

The utility displays:
- Available pools on the backup server
- Snapshots for each pool
- Snapshot dates and sizes

Select the snapshot you want to restore from. Usually, you'll want the most recent one.

### Step 3: Select Destination Disk

The utility scans local disks and displays:
- Device name
- Size
- Current partitions

**⚠️ WARNING**: The selected disk will be completely erased!

Select the disk to restore to. For mirrored setups, you'll restore to one disk first, then add the mirror.

### Step 4: Configure Restore Options

Choose what to restore:

| Option | Description |
|--------|-------------|
| **Restore GPT partition layout** | Recreate partition table from backup |
| **Restore EFI partition** | Restore boot files |
| **Restore ZFS properties** | Apply original mount points, compression, etc. |
| **Install bootloader** | Run grub-install after restore |

### Step 5: Confirm and Execute

Review your selections:
```
Source: backup-server:tank/backups/myhost/ROOT@znapzend-auto-2025-12-29T10:00:00
Target: /dev/nvme0n1
Options:
  - Restore GPT partition layout
  - Restore EFI partition
  - Restore ZFS properties
  - Install bootloader

WARNING: This will DESTROY all data on /dev/nvme0n1!
```

Click **BEGIN RESTORE** to start.

### Step 6: Monitor Progress

The utility shows:
- Current operation
- Progress percentage
- Detailed log output

Wait for completion. This may take a while depending on data size.

### Step 7: Post-Restore

After successful restore:
1. Reboot the system
2. Remove the live USB
3. Boot into your restored system

## Manual Restore

If the interactive utility isn't available, you can restore manually.

### 1. Boot Live Environment

Boot from Ubuntu Live USB or similar.

Install ZFS:
```bash
sudo apt update
sudo apt install zfsutils-linux
```

### 2. Prepare the Disk

**Restore GPT layout:**
```bash
# Copy GPT backup from backup server
scp root@backup-server:/tank/backups/myhost/meta/gpt/nvme0n1.sgdisk /tmp/

# Wipe existing partitions
sgdisk --zap-all /dev/nvme0n1

# Restore partition layout
sgdisk --load-backup=/tmp/nvme0n1.sgdisk /dev/nvme0n1

# Randomize GUIDs (important!)
sgdisk --randomize-guids /dev/nvme0n1

# Inform kernel of changes
partprobe /dev/nvme0n1
```

**Or create partitions manually:**
```bash
# Create EFI partition (512MB)
sgdisk -n 1:0:+512M -t 1:ef00 -c 1:"EFI" /dev/nvme0n1

# Create boot partition (1GB, optional)
sgdisk -n 2:0:+1G -t 2:8300 -c 2:"boot" /dev/nvme0n1

# Create ZFS partition (rest of disk)
sgdisk -n 3:0:0 -t 3:bf00 -c 3:"zfs" /dev/nvme0n1
```

### 3. Create ZFS Pool

**Using saved pool configuration:**
```bash
# View saved pool layout
ssh root@backup-server cat /tank/backups/myhost/meta/zpool/rpool.status

# Create pool (adjust vdev as needed)
zpool create -f -o ashift=12 \
    -O acltype=posixacl \
    -O compression=lz4 \
    -O dnodesize=auto \
    -O normalization=formD \
    -O relatime=on \
    -O xattr=sa \
    -R /mnt \
    rpool /dev/nvme0n1p3
```

### 4. Receive ZFS Datasets

```bash
# Receive root dataset
ssh root@backup-server zfs send -c tank/backups/myhost/ROOT@latest | \
    zfs receive -F rpool/ROOT

# Receive home dataset
ssh root@backup-server zfs send -c tank/backups/myhost/home@latest | \
    zfs receive -F rpool/home

# Receive other datasets as needed
```

### 5. Restore EFI Partition

```bash
# Copy EFI image from backup
scp root@backup-server:/tank/backups/myhost/meta/efi/nvme0n1p1.img /tmp/

# Restore to EFI partition
dd if=/tmp/nvme0n1p1.img of=/dev/nvme0n1p1 bs=4M status=progress
```

### 6. Apply ZFS Properties

```bash
# View saved properties
ssh root@backup-server cat /tank/backups/myhost/meta/zfs/rpool.properties

# Apply properties manually
zfs set mountpoint=/ rpool/ROOT/ubuntu
zfs set mountpoint=/home rpool/home
# ... etc
```

### 7. Fix Boot Configuration

```bash
# Mount necessary filesystems
mount --bind /dev /mnt/dev
mount --bind /proc /mnt/proc
mount --bind /sys /mnt/sys

# Mount EFI partition
mkdir -p /mnt/boot/efi
mount /dev/nvme0n1p1 /mnt/boot/efi

# Chroot into restored system
chroot /mnt

# Regenerate initramfs
update-initramfs -u -k all

# Install GRUB
grub-install --target=x86_64-efi --efi-directory=/boot/efi /dev/nvme0n1
update-grub

# Exit chroot
exit

# Unmount
umount /mnt/boot/efi
umount /mnt/dev /mnt/proc /mnt/sys
zpool export rpool
```

### 8. Reboot

```bash
reboot
```

## Restoring to Different Hardware

When restoring to different hardware:

### Different Disk Size

- If new disk is larger: Works automatically, unused space remains
- If new disk is smaller: May need to adjust partition sizes

### Different Disk Type (SATA vs NVMe)

Update device references:
1. Restore GPT layout
2. Adjust `/etc/fstab` if using device names
3. Update bootloader configuration

### Different Network Hardware

After restore:
1. Check network interface names (`ip link`)
2. Update `/etc/netplan/*.yaml` or network configuration
3. Regenerate initramfs if using network boot

## Restoring Individual Datasets

To restore just specific data without full system restore:

```bash
# Mount the pool temporarily
zpool import -R /mnt rpool

# Restore specific dataset
ssh root@backup-server zfs send -c tank/backups/myhost/home@latest | \
    zfs receive -F rpool/home

# Export pool
zpool export rpool
```

## Troubleshooting

### "Pool already exists"

```bash
# Export existing pool first
zpool export rpool

# Or destroy if you want to replace
zpool destroy rpool
```

### "Cannot receive: dataset already exists"

Use `-F` flag to force:
```bash
zfs receive -F rpool/ROOT
```

### Boot fails after restore

1. Boot back into live environment
2. Import pool: `zpool import -R /mnt rpool`
3. Check/regenerate initramfs
4. Reinstall GRUB
5. Check `/etc/fstab` for correct UUIDs

### Wrong UUIDs in fstab

```bash
# Get new UUIDs
blkid

# Update fstab
nano /mnt/etc/fstab
```

### Network not working after restore

```bash
# Check interface names
ip link

# Update netplan configuration
nano /mnt/etc/netplan/01-netcfg.yaml
```

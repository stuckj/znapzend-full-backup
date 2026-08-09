# Troubleshooting

This guide covers common issues and their solutions.

## Service Issues

### Service Won't Start

**Symptom:** `systemctl start znapzend-full` fails

**Check service status:**
```bash
sudo systemctl status znapzend-full
journalctl -u znapzend-full -e
```

**Common causes:**

1. **Missing configuration file**
   ```bash
   ls -la /etc/znapzend-full/config.yaml
   # If missing, create from example:
   sudo cp /usr/share/doc/znapzend-full/config.yaml.example \
           /etc/znapzend-full/config.yaml
   ```

2. **Invalid configuration**
   ```bash
   sudo znapzend-full-ctl config validate
   ```

3. **znapzend not installed**
   ```bash
   which znapzend
   # Install if missing:
   sudo apt install znapzend  # Debian/Ubuntu
   ```

4. **ZFS not loaded**
   ```bash
   lsmod | grep zfs
   # Load if missing:
   sudo modprobe zfs
   ```

### D-Bus Service Won't Start

**Symptom:** `znapzend-full-ctl` shows "Cannot connect to D-Bus service"

**Check D-Bus service:**
```bash
sudo systemctl status znapzend-full-dbus
journalctl -u znapzend-full-dbus -e
```

**Common causes:**

1. **D-Bus policy not installed**
   ```bash
   ls -la /etc/dbus-1/system.d/org.znapzend.Full.conf
   ```

2. **Python dependencies missing**
   ```bash
   python3 -c "import dbus; print('OK')"
   python3 -c "from gi.repository import GLib; print('OK')"
   ```

3. **Reload D-Bus after installing policy**
   ```bash
   sudo systemctl reload dbus
   ```

## Backup Issues

### Pre-backup Script Fails

**Check logs:**
```bash
cat /var/log/znapzend-full/pre-backup.log
journalctl -u znapzend-full -e
```

**Common causes:**

1. **Metadata dataset doesn't exist**
   ```bash
   zfs list | grep znapzend-full-meta
   # Create if missing:
   sudo zfs create rpool/znapzend-full-meta
   ```

2. **Permission denied on EFI partition**
   ```bash
   # Check if partition exists and is readable
   sudo dd if=/dev/nvme0n1p1 of=/dev/null bs=1 count=1
   ```

3. **sgdisk not installed**
   ```bash
   which sgdisk
   # Install if missing:
   sudo apt install gdisk
   ```

### Backup Never Runs

**Check if paused:**
```bash
znapzend-full-ctl status
```

**Check znapzend status:**
```bash
sudo systemctl status znapzend
znapzendzetup list
```

**Check schedule:**
```bash
znapzendzetup list rpool/ROOT
```

### Backup Stuck "In Progress"

**Check actual znapzend process:**
```bash
ps aux | grep znapzend
```

**Check for network issues to backup server:**
```bash
ssh root@backup-server echo "OK"
```

**Restart services:**
```bash
sudo systemctl restart znapzend-full
sudo systemctl restart znapzend-full-dbus
```

### Metadata Dataset Growing Large

The metadata dataset should stay small due to hash-based change detection.

**Check what's using space:**
```bash
du -sh /rpool/znapzend-full-meta/*
```

**Possible causes:**
1. EFI partition content changing frequently
2. ZFS properties changing often
3. Old snapshots not being cleaned up

**Solution:**
```bash
# Check for unnecessary snapshots
zfs list -t snapshot -r rpool/znapzend-full-meta

# Clean up if needed (careful!)
zfs destroy rpool/znapzend-full-meta@old-snapshot
```

## Connection Issues

### SSH Connection Fails

**Test manually:**
```bash
ssh -v root@backup-server echo "OK"
```

**Common causes:**

1. **Wrong SSH key**
   ```bash
   # Check key exists
   ls -la /root/.ssh/id_backup

   # Test with specific key
   ssh -i /root/.ssh/id_backup root@backup-server echo "OK"
   ```

2. **SSH agent not running**
   ```bash
   eval $(ssh-agent)
   ssh-add /root/.ssh/id_backup
   ```

3. **Firewall blocking connection**
   ```bash
   # Test port connectivity
   nc -zv backup-server 22
   ```

4. **DNS resolution failing**
   ```bash
   # Test with IP instead
   ssh root@192.168.1.100 echo "OK"
   ```

### "Permission denied" on Backup Server

**Check remote permissions:**
```bash
ssh root@backup-server "zfs list tank/backups"
```

**Ensure backup user can:**
- Read source datasets
- Write to destination datasets
- Create snapshots

## GUI Issues

### Tray Icon Not Visible

**KDE:**
```bash
# Check if running
pgrep -f znapzend-full-tray

# Restart
killall znapzend-full-tray
znapzend-full-tray &
```

**GNOME:**
- Install AppIndicator extension
- Enable in GNOME Extensions app

### Configuration Dialog Doesn't Save

**Check Polkit:**
```bash
pkcheck --action-id org.znapzend.full.configure --process $$
```

**Check policy file:**
```bash
ls -la /usr/share/polkit-1/actions/org.znapzend.full.policy
```

### PyQt6 Import Errors

```bash
# Check installation
python3 -c "import PyQt6.QtWidgets; print('OK')"

# Reinstall if needed
pip3 install --force-reinstall PyQt6
```

## Restore Issues

### Cannot Import Pool

**Pool already imported:**
```bash
zpool list
zpool export rpool
```

**Pool was not cleanly exported:**
```bash
zpool import -f rpool
```

### Receive Fails

**"Dataset already exists":**
```bash
zfs receive -F rpool/ROOT  # -F to force
```

**"Insufficient space":**
```bash
zfs list -o name,used,avail
# Free up space or use a larger disk
```

**"Invalid stream":**
- Network issue during transfer
- Try again with fresh connection

### Boot Fails After Restore

1. **Check GRUB installed correctly:**
   ```bash
   # Boot from live USB
   zpool import -R /mnt rpool
   mount /dev/nvme0n1p1 /mnt/boot/efi

   # Chroot and reinstall
   mount --bind /dev /mnt/dev
   mount --bind /proc /mnt/proc
   mount --bind /sys /mnt/sys
   chroot /mnt
   grub-install --target=x86_64-efi --efi-directory=/boot/efi
   update-grub
   exit
   ```

2. **Check initramfs:**
   ```bash
   chroot /mnt update-initramfs -u -k all
   ```

3. **Check fstab:**
   ```bash
   cat /mnt/etc/fstab
   blkid  # Compare UUIDs
   ```

## Log Locations

| Log | Location | Command |
|-----|----------|---------|
| Pre-backup script | `/var/log/znapzend-full/pre-backup.log` | `cat /var/log/znapzend-full/pre-backup.log` |
| Post-backup script | `/var/log/znapzend-full/post-backup.log` | `cat /var/log/znapzend-full/post-backup.log` |
| Main service | systemd journal | `journalctl -u znapzend-full` |
| D-Bus service | systemd journal | `journalctl -u znapzend-full-dbus` |
| znapzend | systemd journal | `journalctl -u znapzend` |

## Getting Help

If you can't resolve an issue:

1. **Gather information:**
   ```bash
   znapzend-full-ctl status --json > status.json
   znapzend-full-ctl config show > config.yaml
   journalctl -u znapzend-full --since "1 hour ago" > service.log
   journalctl -u znapzend-full-dbus --since "1 hour ago" > dbus.log
   ```

2. **Check GitHub issues** for similar problems

3. **Open a new issue** with:
   - Description of the problem
   - Steps to reproduce
   - Log output
   - Configuration (remove sensitive data)
   - System information:
     ```bash
     uname -a
     zfs version
     python3 --version
     ```

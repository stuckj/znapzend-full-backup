# Hash-Based Change Detection

This document explains the hash tracking system used to efficiently backup non-ZFS data.

## Problem

Non-ZFS data (EFI partitions, GPT layouts, ZFS properties) changes infrequently. Without change detection:

1. Every backup would update these files
2. ZFS snapshots would store redundant copies
3. Backup storage would grow unnecessarily

## Solution

Hash-based change detection ensures files are only updated when content actually changes.

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                    Backup Process                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Source Data          Temp File           Target File      │
│   (e.g., EFI)                                               │
│       │                                                     │
│       ▼                                                     │
│   ┌───────┐                                                 │
│   │  dd   │──────────►  /tmp/efi.img.tmp                   │
│   └───────┘                                                 │
│                              │                              │
│                              ▼                              │
│                        ┌──────────┐                         │
│                        │ SHA256   │                         │
│                        │ compute  │                         │
│                        └────┬─────┘                         │
│                             │                               │
│                             ▼                               │
│                     new_hash = "abc123..."                  │
│                             │                               │
│                             ▼                               │
│                    ┌────────────────┐                       │
│                    │  Read stored   │                       │
│                    │  hash file     │                       │
│                    └────────┬───────┘                       │
│                             │                               │
│                             ▼                               │
│                   stored_hash = "abc123..."                 │
│                             │                               │
│                             ▼                               │
│                    ┌────────────────┐                       │
│                    │ new == stored? │                       │
│                    └────────┬───────┘                       │
│                             │                               │
│              ┌──────────────┴──────────────┐                │
│              │                             │                │
│              ▼                             ▼                │
│           YES                            NO                 │
│              │                             │                │
│              ▼                             ▼                │
│       Delete temp file            Move temp → target        │
│       (no change)                 Update hash file          │
│                                   (content changed)         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Implementation

### HashTracker Class

```python
class HashTracker:
    def __init__(self, base_path: Path):
        """Initialize with metadata dataset mountpoint."""
        self.base_path = base_path

    def update_file(
        self,
        relative_path: str,
        content_generator: Callable[[Path], None],
    ) -> bool:
        """Update a file if its content has changed.

        Args:
            relative_path: Path relative to base_path
            content_generator: Function that writes content to a path

        Returns:
            True if file was updated, False if unchanged
        """
        target_path = self.base_path / relative_path
        hash_path = target_path.with_suffix(target_path.suffix + ".sha256")

        # Write to temp file
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)

        content_generator(tmp_path)

        # Compute hash
        new_hash = compute_sha256(tmp_path)
        stored_hash = self._read_stored_hash(hash_path)

        if new_hash == stored_hash:
            tmp_path.unlink()  # No change
            return False
        else:
            shutil.move(tmp_path, target_path)
            hash_path.write_text(f"{new_hash}  {target_path.name}\n")
            return True
```

### Hash File Format

Hash files use the standard `sha256sum` format:

```
abc123def456...  filename.ext
```

This allows verification with standard tools:
```bash
cd /rpool/znapzend-full-meta/efi
sha256sum -c nvme0n1p1.img.sha256
```

## File Structure

```
/rpool/znapzend-full-meta/
├── efi/
│   ├── nvme0n1p1.img           # EFI partition image
│   └── nvme0n1p1.img.sha256    # Hash file
├── gpt/
│   ├── nvme0n1.sgdisk          # Binary GPT backup
│   ├── nvme0n1.sgdisk.sha256
│   ├── nvme0n1.txt             # Human-readable GPT
│   └── nvme0n1.txt.sha256
├── zpool/
│   ├── rpool.status            # vdev layout
│   ├── rpool.status.sha256
│   ├── rpool.properties        # Pool properties
│   └── rpool.properties.sha256
└── zfs/
    ├── rpool.properties        # Dataset properties
    └── rpool.properties.sha256
```

## Why This Works with ZFS

ZFS copy-on-write means:
- If a file doesn't change, snapshots share blocks
- Only changed blocks use additional space
- Our hash tracking prevents unnecessary file updates

```
Snapshot 1: [file.img] ──────────► [block A]
                                       │
Snapshot 2: [file.img] ────────────────┘  (shared, no change)

Snapshot 3: [file.img] ──────────► [block B]  (content changed)
```

## Performance Considerations

### Hash Computation

SHA256 is computed once per backup:
- EFI partition (~512MB): ~1-2 seconds
- GPT layout (~1KB): negligible
- ZFS properties (~100KB): negligible

### Disk I/O

Temp files are written to the same filesystem (metadata dataset), minimizing I/O:

```python
with tempfile.NamedTemporaryFile(
    delete=False,
    dir=target_path.parent,  # Same directory
    prefix=f".{target_path.name}.",
) as tmp:
```

### Atomic Updates

File replacement is atomic via `rename()`:
- Either the old file exists, or the new one does
- Never a partial or corrupted state

## Edge Cases

### First Backup

No stored hash exists, so the file is always written:

```python
stored_hash = self._read_stored_hash(hash_path)
if stored_hash is None:
    return True  # Treat as changed
```

### Hash File Missing

If the hash file is deleted but the data file exists:
- Hash is recomputed
- If data hasn't changed, hash file is recreated
- If data changed, both files are updated

### Orphaned Hash Files

Hash files without corresponding data files can be cleaned up:

```python
def cleanup_orphaned_hashes(self) -> list[Path]:
    """Remove hash files without data files."""
    removed = []
    for hash_path in self.base_path.rglob("*.sha256"):
        data_path = hash_path.with_suffix("")
        if not data_path.exists():
            hash_path.unlink()
            removed.append(hash_path)
    return removed
```

## Text File Optimization

For text content (properties, GPT layout), we can hash the string directly:

```python
def update_text_file(self, relative_path: str, content: str) -> bool:
    """Update a text file if content changed."""
    new_hash = hashlib.sha256(content.encode()).hexdigest()
    stored_hash = self._read_stored_hash(hash_path)

    if new_hash == stored_hash:
        return False

    target_path.write_text(content)
    hash_path.write_text(f"{new_hash}  {target_path.name}\n")
    return True
```

This avoids writing temp files for small text content.

## Bash Implementation

The pre-backup script uses this pattern:

```bash
update_with_hash() {
    local target="$1"
    local tmp_file="$2"
    local hash_file="${target}.sha256"

    local new_hash
    new_hash=$(sha256sum "$tmp_file" | cut -d' ' -f1)

    local stored_hash=""
    if [[ -f "$hash_file" ]]; then
        stored_hash=$(cut -d' ' -f1 < "$hash_file")
    fi

    if [[ "$new_hash" != "$stored_hash" ]]; then
        mv "$tmp_file" "$target"
        echo "$new_hash  $(basename "$target")" > "$hash_file"
        return 0  # Changed
    else
        rm -f "$tmp_file"
        return 1  # Unchanged
    fi
}
```

## Verification

Verify backup integrity:

```bash
#!/bin/bash
# verify-metadata.sh

cd /rpool/znapzend-full-meta

echo "Verifying EFI backups..."
(cd efi && sha256sum -c *.sha256)

echo "Verifying GPT backups..."
(cd gpt && sha256sum -c *.sha256)

echo "Verifying zpool backups..."
(cd zpool && sha256sum -c *.sha256)

echo "Verifying ZFS property backups..."
(cd zfs && sha256sum -c *.sha256)
```

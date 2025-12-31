# znapzend-full Design Documentation

This documentation covers the architecture, design decisions, and implementation details of znapzend-full. It's intended for developers who want to understand, modify, or contribute to the project.

## Table of Contents

1. [Architecture Overview](architecture.md)
2. [Component Design](components.md)
3. [Data Flow](data-flow.md)
4. [Configuration System](configuration.md)
5. [D-Bus Interface](dbus-interface.md)
6. [Hash-Based Change Detection](hash-tracking.md)
7. [Restore System](restore-system.md)
8. [E2E Testing Framework](e2e-testing.md)
9. [Packaging](packaging.md)
10. [Contributing](contributing.md)

## Project Goals

### Primary Goals

1. **Complete System Restore** - Provide everything needed to restore a system from backup without manual intervention
2. **Transparency** - Build on top of znapzend without modifying it
3. **Multiple Interfaces** - Support both desktop (GUI) and headless (CLI) environments
4. **Efficiency** - Minimize backup storage through hash-based change detection

### Non-Goals

- Replacing znapzend (we wrap it, not replace it)
- Cross-platform support (Linux-only)
- Backing up non-ZFS filesystems (except EFI)

## Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Pre/post scripts | Bash | Simple, no dependencies, runs early in boot |
| Core logic | Python 3.9+ | Modern features, good library support |
| CLI | Python argparse | Built-in, sufficient for our needs |
| GUI | PyQt6 | Native KDE integration, cross-desktop |
| IPC | D-Bus | Standard Linux IPC, systemd integration |
| Authorization | Polkit | Standard privilege escalation |
| Restore TUI | Textual | Modern terminal UI framework |
| Config format | YAML | Human-readable, widely supported |

## Project Structure

```
znapzend-full/
├── bin/                          # Executable scripts
│   ├── znapzend-full-pre-backup  # Bash: pre-backup hook
│   └── znapzend-full-post-backup # Bash: post-backup hook
├── src/znapzend_full/            # Python package
│   ├── __init__.py
│   ├── config.py                 # Configuration management
│   ├── utils.py                  # Shared utilities
│   ├── dbus_service.py           # D-Bus service daemon
│   ├── backup/                   # Backup operations
│   │   ├── efi.py                # EFI partition backup
│   │   ├── partition.py          # GPT backup
│   │   ├── zfs_props.py          # ZFS properties backup
│   │   └── hash_tracker.py       # Change detection
│   ├── restore/                  # Restore operations
│   │   ├── interactive.py        # Textual TUI
│   │   ├── ssh_client.py         # SSH operations
│   │   ├── zfs_restore.py        # ZFS restore
│   │   └── partition_restore.py  # GPT/EFI restore
│   └── cli/                      # CLI tool
│       └── ctl.py                # znapzend-full-ctl
├── ui/znapzend_full/             # GUI package
│   ├── tray.py                   # System tray app
│   └── config_dialog.py          # Configuration dialog
├── systemd/                      # Service files
├── dbus/                         # D-Bus policy
├── polkit/                       # Polkit policy
├── config/                       # Example configuration
├── packaging/                    # Package specs
│   ├── debian/
│   └── rpm/
├── tests/                        # Test suite
└── docs/                         # Documentation
```

## Key Design Decisions

### 1. Wrapper Architecture

znapzend-full wraps znapzend rather than forking or replacing it:

**Pros:**
- Benefit from znapzend updates automatically
- No need to maintain ZFS send/receive logic
- Users can still use znapzend directly

**Cons:**
- Limited control over backup process
- Must work within znapzend's model

### 2. Hash-Based Change Detection

Non-ZFS backups (EFI, GPT, properties) use hash tracking:

```
File → Temp Location → SHA256 → Compare with stored hash
                                    ↓
                            Same? → Discard temp file
                            Diff? → Replace file + update hash
```

This ensures ZFS snapshots don't waste space on unchanged metadata.

### 3. D-Bus for IPC

We use D-Bus for communication between components:

```
┌─────────┐      D-Bus (System Bus)     ┌─────────────┐
│  Tray   │◄────────────────────────────►│   Service   │
│   App   │                              │   (root)    │
└─────────┘                              └─────────────┘
     ▲                                         ▲
     │         D-Bus (System Bus)              │
     │                                         │
┌─────────┐                              ┌─────────────┐
│   CLI   │◄────────────────────────────►│   Scripts   │
│  Tool   │                              │ (pre/post)  │
└─────────┘                              └─────────────┘
```

### 4. Separate GUI Package

GUI components (PyQt6) are optional:
- Core functionality works without GUI
- Headless systems don't need Qt dependencies
- Reduces attack surface on servers

### 5. Polkit for Authorization

Privileged operations use Polkit:
- Users get prompted for authentication
- Configurable policies per-action
- Integration with desktop environments

## Development Setup

```bash
# Clone repository
git clone https://github.com/yourusername/znapzend-full.git
cd znapzend-full

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check src/
mypy src/
```

## Testing

### Unit Tests

```bash
pytest tests/unit/
```

### Integration Tests

Requires ZFS:
```bash
pytest tests/integration/
```

### E2E Tests

Full backup/restore cycle using QEMU VMs. Requires KVM and ~8GB RAM:
```bash
# Build base image (first time)
cd tests/e2e/images && make image

# Run E2E tests
pytest tests/e2e/ -v --timeout=1200
```

See [E2E Testing Framework](e2e-testing.md) for details.

### Manual Testing

```bash
# Run D-Bus service on session bus (no root required)
python -m znapzend_full.dbus_service --session-bus

# Run CLI against session bus
znapzend-full-ctl --session-bus status

# Run tray against session bus
znapzend-full-tray --session-bus
```

## Code Style

- Python: Black + isort + ruff
- Line length: 100 characters
- Type hints: Required for public APIs
- Docstrings: Google style

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2025-12 | Initial implementation |

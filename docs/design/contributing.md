# Contributing Guide

Thank you for your interest in contributing to znapzend-full!

## Getting Started

### Prerequisites

- Python 3.9+
- ZFS (for integration testing)
- Git

### Development Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/znapzend-full.git
cd znapzend-full

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in development mode with dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks (optional)
pre-commit install
```

### Running Without Installation

```bash
# Run D-Bus service on session bus
python -m znapzend_full.dbus_service --session-bus

# Run CLI
python -m znapzend_full.cli.ctl --session-bus status

# Run tray app
python -m znapzend_full.ui.tray --session-bus

# Run restore TUI
python -m znapzend_full.restore.interactive
```

## Project Structure

```
znapzend-full/
├── bin/                    # Shell scripts
├── src/znapzend_full/      # Main Python package
│   ├── backup/             # Backup operations
│   ├── restore/            # Restore operations
│   └── cli/                # CLI tool
├── ui/znapzend_full/       # GUI package (separate)
├── tests/                  # Test suite
├── docs/                   # Documentation
└── packaging/              # Package specs
```

## Code Style

### Python

We use:
- **Black** for formatting
- **isort** for import sorting
- **ruff** for linting
- **mypy** for type checking

```bash
# Format code
black src/ ui/ tests/
isort src/ ui/ tests/

# Lint
ruff check src/ ui/

# Type check
mypy src/
```

### Configuration

```toml
# pyproject.toml
[tool.black]
line-length = 100

[tool.isort]
profile = "black"
line_length = 100

[tool.ruff]
line-length = 100
target-version = "py39"
```

### Shell Scripts

- Use `shellcheck` for linting
- Use `set -euo pipefail` at the start
- Quote variables: `"$var"` not `$var`

```bash
shellcheck bin/znapzend-full-*
```

## Testing

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=znapzend_full --cov-report=html

# Specific test file
pytest tests/test_config.py

# Verbose output
pytest -v
```

### Test Structure

```
tests/
├── unit/                   # Unit tests (no ZFS required)
│   ├── test_config.py
│   ├── test_hash_tracker.py
│   └── test_utils.py
├── integration/            # Integration tests (ZFS required)
│   ├── test_backup.py
│   └── test_restore.py
└── conftest.py             # Shared fixtures
```

### Writing Tests

```python
# tests/unit/test_config.py

import pytest
from znapzend_full.config import Config, load_config, validate_config

class TestConfig:
    def test_default_config(self):
        config = Config()
        assert config.version == 1
        assert config.metadata_dataset == "rpool/znapzend-full-meta"

    def test_load_config_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.yaml")

    def test_validate_empty_dataset_name(self):
        config = Config()
        config.datasets.append(DatasetConfig(name=""))
        errors = validate_config(config)
        assert any("name is required" in e for e in errors)
```

### Fixtures

```python
# tests/conftest.py

import pytest
from pathlib import Path

@pytest.fixture
def sample_config():
    return {
        "version": 1,
        "metadata_dataset": "testpool/meta",
        "datasets": [
            {"name": "testpool/data", "destination": "backup:tank/backup"}
        ],
    }

@pytest.fixture
def config_file(tmp_path, sample_config):
    import yaml
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(sample_config))
    return config_path
```

## Documentation

### User Documentation

Located in `docs/usage/`. Written for end users:
- Clear, step-by-step instructions
- Avoid implementation details
- Include examples and screenshots

### Design Documentation

Located in `docs/design/`. Written for developers:
- Explain architecture decisions
- Include diagrams
- Document interfaces

### Docstrings

Use Google style:

```python
def backup_efi_partitions(
    partitions: list[str],
    tracker: HashTracker,
) -> dict[str, bool]:
    """Backup multiple EFI partitions.

    Args:
        partitions: List of device paths (e.g., ['/dev/nvme0n1p1']).
        tracker: HashTracker for change detection.

    Returns:
        Dict mapping partition to whether it was updated.

    Raises:
        PermissionError: If partition is not readable.
    """
```

## Submitting Changes

### Branch Naming

- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation
- `refactor/description` - Code refactoring

### Commit Messages

Follow conventional commits:

```
type(scope): description

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `refactor`: Code refactoring
- `test`: Tests
- `chore`: Maintenance

Examples:
```
feat(backup): add support for multiple EFI partitions

fix(dbus): handle connection timeout gracefully

docs(usage): add troubleshooting section
```

### Pull Request Process

1. **Fork** the repository
2. **Create** a feature branch
3. **Make** your changes
4. **Test** your changes
5. **Submit** a pull request

PR checklist:
- [ ] Tests pass (`pytest`)
- [ ] Code is formatted (`black`, `isort`)
- [ ] Linting passes (`ruff`, `mypy`)
- [ ] Documentation updated if needed
- [ ] Commit messages follow convention

### Code Review

Expect feedback on:
- Code correctness
- Test coverage
- Documentation
- Performance implications
- Security considerations

## Adding New Features

### New Backup Type

1. Create module in `src/znapzend_full/backup/`
2. Add to `backup/__init__.py`
3. Update pre-backup script
4. Add configuration options
5. Update documentation
6. Add tests

### New CLI Command

1. Add handler in `src/znapzend_full/cli/ctl.py`
2. Register subparser
3. Update CLI documentation
4. Add tests

### New D-Bus Method

1. Add method to `dbus_service.py`
2. Update D-Bus interface documentation
3. Update Polkit policy if privileged
4. Add tests

## Release Process

1. Update version in `pyproject.toml` and `__init__.py`
2. Update changelog
3. Create release commit
4. Tag release
5. Build packages
6. Upload to package repositories

## Getting Help

- **Questions**: Open a GitHub discussion
- **Bugs**: Open a GitHub issue
- **Security**: Email maintainers directly

## Code of Conduct

Be respectful and constructive. We're all here to make backup software better.

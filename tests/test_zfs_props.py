"""Tests for znapzend_full.backup.zfs_props module."""

import pytest
from pathlib import Path

from znapzend_full.backup.zfs_props import (
    parse_zfs_properties,
    parse_zpool_properties,
    get_restore_commands,
)


class TestParseZfsProperties:
    """Tests for parse_zfs_properties function."""

    def test_parse_basic_properties(self, sample_zfs_properties):
        result = parse_zfs_properties(sample_zfs_properties)

        assert "testpool" in result
        assert "testpool/ROOT" in result
        assert "testpool/home" in result

    def test_filters_local_properties(self, sample_zfs_properties):
        result = parse_zfs_properties(sample_zfs_properties)

        # Local properties should be included
        assert result["testpool"].get("compression") == "lz4"
        assert result["testpool"].get("mountpoint") == "/testpool"
        assert result["testpool"].get("atime") == "off"

    def test_excludes_default_properties(self):
        content = """NAME\tPROPERTY\tVALUE\tSOURCE
testpool\tcompression\toff\tdefault
testpool\tmountpoint\t/testpool\tlocal
"""
        result = parse_zfs_properties(content)

        # Default properties should be excluded
        assert "compression" not in result["testpool"]
        # Local properties should be included
        assert result["testpool"]["mountpoint"] == "/testpool"

    def test_handles_inherited_properties(self, sample_zfs_properties):
        result = parse_zfs_properties(sample_zfs_properties)

        # Inherited properties should not be stored (they'll be inherited after restore)
        # Only local properties from the child dataset should be present
        assert result["testpool/ROOT"].get("mountpoint") == "/"

    def test_empty_input(self):
        result = parse_zfs_properties("")
        assert result == {}

    def test_header_only(self):
        content = "NAME\tPROPERTY\tVALUE\tSOURCE\n"
        result = parse_zfs_properties(content)
        assert result == {}

    def test_dash_source(self):
        """Properties with '-' source (like type) should be included."""
        content = """NAME\tPROPERTY\tVALUE\tSOURCE
testpool\ttype\tfilesystem\t-
"""
        result = parse_zfs_properties(content)
        assert result["testpool"]["type"] == "filesystem"


class TestParseZpoolProperties:
    """Tests for parse_zpool_properties function."""

    def test_parse_local_properties(self):
        content = """NAME\tPROPERTY\tVALUE\tSOURCE
testpool\tashift\t12\tlocal
testpool\tautoreplace\ton\tlocal
testpool\tcomment\t-\tdefault
testpool\tsize\t1T\t-
"""
        result = parse_zpool_properties(content)

        assert result["ashift"] == "12"
        assert result["autoreplace"] == "on"
        # Default and non-local properties should be excluded
        assert "comment" not in result
        assert "size" not in result

    def test_empty_input(self):
        result = parse_zpool_properties("")
        assert result == {}

    def test_header_only(self):
        content = "NAME\tPROPERTY\tVALUE\tSOURCE\n"
        result = parse_zpool_properties(content)
        assert result == {}


class TestGetRestoreCommands:
    """Tests for get_restore_commands function."""

    def test_generates_set_commands(self, temp_dir, sample_zfs_properties):
        props_file = temp_dir / "test.properties"
        props_file.write_text(sample_zfs_properties)

        commands = get_restore_commands(props_file)

        # Should generate zfs set commands for local properties
        assert any("zfs set compression=lz4 testpool" in cmd for cmd in commands)
        assert any("zfs set mountpoint=/testpool testpool" in cmd for cmd in commands)
        assert any("zfs set atime=off testpool" in cmd for cmd in commands)

    def test_excludes_readonly_properties(self, temp_dir):
        content = """NAME\tPROPERTY\tVALUE\tSOURCE
testpool\tcompression\tlz4\tlocal
testpool\tused\t100G\t-
testpool\tavailable\t500G\t-
testpool\tguid\t12345\t-
"""
        props_file = temp_dir / "test.properties"
        props_file.write_text(content)

        commands = get_restore_commands(props_file)

        # Readonly properties should not have set commands
        assert not any("used=" in cmd for cmd in commands)
        assert not any("available=" in cmd for cmd in commands)
        assert not any("guid=" in cmd for cmd in commands)
        # Writable properties should have set commands
        assert any("compression=lz4" in cmd for cmd in commands)

    def test_target_pool_replacement(self, temp_dir, sample_zfs_properties):
        props_file = temp_dir / "test.properties"
        props_file.write_text(sample_zfs_properties)

        commands = get_restore_commands(props_file, target_pool="newpool")

        # Pool name should be replaced in dataset targets
        assert any("newpool" in cmd for cmd in commands)
        # Check that commands target the new pool/datasets
        assert any(cmd.endswith(" newpool") for cmd in commands)
        assert any(cmd.endswith(" newpool/ROOT") for cmd in commands)
        assert any(cmd.endswith(" newpool/home") for cmd in commands)
        # Dataset targets should use new pool name (not the old one)
        assert not any(cmd.endswith(" testpool") for cmd in commands)
        assert not any(cmd.endswith(" testpool/ROOT") for cmd in commands)
        assert not any(cmd.endswith(" testpool/home") for cmd in commands)

    def test_nonexistent_file(self, temp_dir):
        commands = get_restore_commands(temp_dir / "nonexistent.properties")
        assert commands == []

    def test_empty_file(self, temp_dir):
        props_file = temp_dir / "empty.properties"
        props_file.write_text("")

        commands = get_restore_commands(props_file)
        assert commands == []

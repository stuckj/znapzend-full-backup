"""Tests for znapzend_full.cli.ctl module."""

import json
import argparse

from znapzend_full.cli.ctl import (
    format_status,
    cmd_config_show,
    cmd_config_validate,
    cmd_dataset_list,
    cmd_dest_list,
)
from znapzend_full.config import Config, save_config


class TestFormatStatus:
    """Tests for format_status function."""

    def test_idle_status(self):
        status = {"state": "idle"}
        result = format_status(status)

        assert "IDLE" in result
        assert "\u2713" in result  # checkmark

    def test_backing_up_status(self):
        status = {
            "state": "backing_up",
            "current_dataset": "rpool/ROOT",
            "progress_percent": 45,
        }
        result = format_status(status)

        assert "BACKING_UP" in result
        assert "rpool/ROOT" in result
        assert "45%" in result

    def test_paused_status(self):
        status = {"state": "paused", "paused": True}
        result = format_status(status)

        assert "PAUSED" in result
        assert "paused" in result.lower()

    def test_error_status(self):
        status = {
            "state": "error",
            "error_message": "Connection refused",
        }
        result = format_status(status)

        assert "ERROR" in result
        assert "Connection refused" in result

    def test_with_timestamps(self):
        status = {
            "state": "idle",
            "last_backup": "2025-12-29T10:30:00",
            "next_scheduled": "2025-12-29T11:00:00",
        }
        result = format_status(status)

        assert "2025-12-29T10:30:00" in result
        assert "2025-12-29T11:00:00" in result

    def test_json_output(self):
        status = {"state": "idle", "paused": False}
        result = format_status(status, use_json=True)

        parsed = json.loads(result)
        assert parsed["state"] == "idle"
        assert parsed["paused"] is False


class TestConfigShow:
    """Tests for cmd_config_show command."""

    def test_show_existing_config(self, temp_dir, sample_config_dict, capsys):
        from znapzend_full.config import Config, save_config

        config_path = temp_dir / "config.yaml"
        config = Config.from_dict(sample_config_dict)
        save_config(config, config_path)

        args = argparse.Namespace(
            config=str(config_path),
            json=False,
            session_bus=False,
        )

        result = cmd_config_show(args)
        captured = capsys.readouterr()

        assert result == 0
        assert "version:" in captured.out.lower() or "version" in captured.out

    def test_show_missing_config(self, temp_dir, capsys):
        args = argparse.Namespace(
            config=str(temp_dir / "nonexistent.yaml"),
            json=False,
            session_bus=False,
        )

        result = cmd_config_show(args)
        captured = capsys.readouterr()

        assert result == 1
        assert "not found" in captured.err

    def test_show_json_output(self, temp_dir, sample_config_dict, capsys):
        from znapzend_full.config import Config, save_config

        config_path = temp_dir / "config.yaml"
        config = Config.from_dict(sample_config_dict)
        save_config(config, config_path)

        args = argparse.Namespace(
            config=str(config_path),
            json=True,
            session_bus=False,
        )

        result = cmd_config_show(args)
        captured = capsys.readouterr()

        assert result == 0
        parsed = json.loads(captured.out)
        assert parsed["version"] == 1


class TestConfigValidate:
    """Tests for cmd_config_validate command."""

    def test_validate_valid_config(self, temp_dir, sample_config_dict, capsys):
        config_path = temp_dir / "config.yaml"
        config = Config.from_dict(sample_config_dict)
        save_config(config, config_path)

        args = argparse.Namespace(
            config=str(config_path),
            session_bus=False,
        )

        result = cmd_config_validate(args)
        captured = capsys.readouterr()

        assert result == 0
        assert "valid" in captured.out.lower()

    def test_validate_missing_config(self, temp_dir, capsys):
        args = argparse.Namespace(
            config=str(temp_dir / "nonexistent.yaml"),
            session_bus=False,
        )

        result = cmd_config_validate(args)
        captured = capsys.readouterr()

        assert result == 1
        assert "not found" in captured.err

    def test_validate_invalid_config(self, temp_dir, capsys):
        config_path = temp_dir / "config.yaml"
        # Create config with invalid version
        config = Config(version=99)
        save_config(config, config_path)

        args = argparse.Namespace(
            config=str(config_path),
            session_bus=False,
        )

        result = cmd_config_validate(args)
        captured = capsys.readouterr()

        assert result == 1
        assert "error" in captured.err.lower()


class TestDatasetList:
    """Tests for cmd_dataset_list command."""

    def test_list_configured_datasets(self, temp_dir, sample_config_dict, capsys):
        config_path = temp_dir / "config.yaml"
        config = Config.from_dict(sample_config_dict)
        save_config(config, config_path)

        args = argparse.Namespace(
            config=str(config_path),
            json=False,
            session_bus=False,
        )

        result = cmd_dataset_list(args)
        captured = capsys.readouterr()

        assert result == 0
        assert "testpool/ROOT" in captured.out
        assert "testpool/home" in captured.out

    def test_list_datasets_json(self, temp_dir, sample_config_dict, capsys):
        config_path = temp_dir / "config.yaml"
        config = Config.from_dict(sample_config_dict)
        save_config(config, config_path)

        args = argparse.Namespace(
            config=str(config_path),
            json=True,
            session_bus=False,
        )

        result = cmd_dataset_list(args)
        captured = capsys.readouterr()

        assert result == 0
        parsed = json.loads(captured.out)
        assert len(parsed) == 2
        assert parsed[0]["name"] == "testpool/ROOT"

    def test_list_empty_datasets(self, temp_dir, capsys):
        config_path = temp_dir / "config.yaml"
        config = Config()
        save_config(config, config_path)

        args = argparse.Namespace(
            config=str(config_path),
            json=False,
            session_bus=False,
        )

        result = cmd_dataset_list(args)
        captured = capsys.readouterr()

        assert result == 0
        assert "No datasets configured" in captured.out


class TestDestList:
    """Tests for cmd_dest_list command."""

    def test_list_configured_destinations(self, temp_dir, sample_config_dict, capsys):
        config_path = temp_dir / "config.yaml"
        config = Config.from_dict(sample_config_dict)
        save_config(config, config_path)

        args = argparse.Namespace(
            config=str(config_path),
            json=False,
            session_bus=False,
        )

        result = cmd_dest_list(args)
        captured = capsys.readouterr()

        assert result == 0
        assert "backup-server" in captured.out
        assert "backup.local" in captured.out

    def test_list_destinations_json(self, temp_dir, sample_config_dict, capsys):
        config_path = temp_dir / "config.yaml"
        config = Config.from_dict(sample_config_dict)
        save_config(config, config_path)

        args = argparse.Namespace(
            config=str(config_path),
            json=True,
            session_bus=False,
        )

        result = cmd_dest_list(args)
        captured = capsys.readouterr()

        assert result == 0
        parsed = json.loads(captured.out)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "backup-server"
        assert parsed[0]["host"] == "backup.local"

    def test_list_no_destinations(self, temp_dir, capsys):
        config_path = temp_dir / "config.yaml"
        config = Config()
        save_config(config, config_path)

        args = argparse.Namespace(
            config=str(config_path),
            json=False,
            session_bus=False,
        )

        result = cmd_dest_list(args)
        captured = capsys.readouterr()

        assert result == 0
        assert "No destinations configured" in captured.out

    def test_list_missing_config(self, temp_dir, capsys):
        args = argparse.Namespace(
            config=str(temp_dir / "nonexistent.yaml"),
            json=False,
            session_bus=False,
        )

        result = cmd_dest_list(args)
        captured = capsys.readouterr()

        assert result == 1
        assert "not found" in captured.err.lower() or "No configuration" in captured.err

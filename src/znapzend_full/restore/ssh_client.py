"""
SSH client for remote backup access.

Provides SSH operations for accessing remote backup servers.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SSHConfig:
    """SSH connection configuration."""
    host: str
    user: str = "root"
    port: int = 22
    ssh_key: str = ""

    def ssh_command(self) -> list[str]:
        """Build base SSH command."""
        cmd = ["ssh"]
        if self.ssh_key:
            cmd.extend(["-i", self.ssh_key])
        cmd.extend(["-p", str(self.port)])
        cmd.extend(["-o", "BatchMode=yes"])
        cmd.extend(["-o", "StrictHostKeyChecking=accept-new"])
        return cmd

    def connection_string(self) -> str:
        """Get user@host string."""
        return f"{self.user}@{self.host}"


class SSHClient:
    """Client for SSH operations to backup server."""

    def __init__(self, config: SSHConfig):
        """Initialize SSH client.

        Args:
            config: SSH connection configuration.
        """
        self.config = config

    def test_connection(self) -> tuple[bool, str]:
        """Test SSH connection.

        Returns:
            Tuple of (success, message).
        """
        cmd = self.config.ssh_command()
        cmd.extend([
            "-o", "ConnectTimeout=10",
            self.config.connection_string(),
            "echo", "Connection successful"
        ])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                return True, "Connection successful"
            else:
                return False, result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "Connection timed out"
        except Exception as e:
            return False, str(e)

    def run_command(
        self,
        command: str,
        timeout: int = 60,
    ) -> subprocess.CompletedProcess:
        """Run a command on the remote server.

        Args:
            command: Command to run.
            timeout: Timeout in seconds.

        Returns:
            CompletedProcess with result.
        """
        cmd = self.config.ssh_command()
        cmd.extend([self.config.connection_string(), command])

        logger.debug(f"Running remote command: {command}")
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def list_snapshots(self, dataset: str) -> list[str]:
        """List snapshots for a dataset on remote server.

        Args:
            dataset: Dataset name.

        Returns:
            List of snapshot names.
        """
        result = self.run_command(
            f"zfs list -H -t snapshot -o name -r {dataset}"
        )
        if result.returncode != 0:
            logger.error(f"Failed to list snapshots: {result.stderr}")
            return []

        return [line.strip() for line in result.stdout.split("\n") if line.strip()]

    def list_datasets(self, pool: str = "") -> list[dict]:
        """List datasets on remote server.

        Args:
            pool: Pool name (optional).

        Returns:
            List of dataset info dicts.
        """
        cmd = "zfs list -H -o name,mountpoint,used,type"
        if pool:
            cmd += f" -r {pool}"

        result = self.run_command(cmd)
        if result.returncode != 0:
            logger.error(f"Failed to list datasets: {result.stderr}")
            return []

        datasets = []
        for line in result.stdout.split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 4:
                datasets.append({
                    "name": parts[0],
                    "mountpoint": parts[1] if parts[1] != "-" else None,
                    "used": parts[2],
                    "type": parts[3],
                })

        return datasets

    def list_pools(self) -> list[str]:
        """List ZFS pools on remote server.

        Returns:
            List of pool names.
        """
        result = self.run_command("zpool list -H -o name")
        if result.returncode != 0:
            logger.error(f"Failed to list pools: {result.stderr}")
            return []

        return [line.strip() for line in result.stdout.split("\n") if line.strip()]

    def get_snapshot_info(self, snapshot: str) -> dict | None:
        """Get information about a specific snapshot.

        Args:
            snapshot: Snapshot name.

        Returns:
            Dict with snapshot info or None.
        """
        result = self.run_command(
            f"zfs get -H -o property,value creation,used,referenced {snapshot}"
        )
        if result.returncode != 0:
            return None

        info = {"name": snapshot}
        for line in result.stdout.split("\n"):
            parts = line.split("\t")
            if len(parts) >= 2:
                info[parts[0]] = parts[1]

        return info

    def read_file(self, path: str) -> str | None:
        """Read a file from remote server.

        Args:
            path: File path.

        Returns:
            File contents or None on error.
        """
        result = self.run_command(f"cat {path}")
        if result.returncode != 0:
            return None
        return result.stdout

    def file_exists(self, path: str) -> bool:
        """Check if a file exists on remote server.

        Args:
            path: File path.

        Returns:
            True if file exists.
        """
        result = self.run_command(f"test -f {path} && echo yes || echo no")
        return result.stdout.strip() == "yes"

    def list_metadata_files(self, metadata_path: str) -> dict[str, list[str]]:
        """List metadata files in the backup.

        Args:
            metadata_path: Path to metadata directory.

        Returns:
            Dict with categories and files.
        """
        files = {
            "efi": [],
            "gpt": [],
            "zpool": [],
            "zfs": [],
        }

        for category in files.keys():
            path = f"{metadata_path}/{category}"
            result = self.run_command(f"ls -1 {path} 2>/dev/null || true")
            if result.returncode == 0:
                files[category] = [
                    f for f in result.stdout.split("\n")
                    if f.strip() and not f.endswith(".sha256")
                ]

        return files

    def stream_receive(
        self,
        snapshot: str,
        local_dataset: str,
        force: bool = False,
    ) -> subprocess.CompletedProcess:
        """Receive a snapshot stream from remote.

        Args:
            snapshot: Remote snapshot name.
            local_dataset: Local dataset to receive into.
            force: Force rollback if needed.

        Returns:
            CompletedProcess result.
        """
        # Build zfs send | zfs receive pipeline
        send_cmd = f"zfs send -c {snapshot}"  # -c for compressed stream

        recv_cmd = ["zfs", "receive"]
        if force:
            recv_cmd.append("-F")
        recv_cmd.append(local_dataset)

        ssh_cmd = self.config.ssh_command()
        ssh_cmd.extend([self.config.connection_string(), send_cmd])

        # Create pipeline: ssh zfs send | zfs receive
        logger.info(f"Receiving {snapshot} into {local_dataset}")

        send_proc = subprocess.Popen(
            ssh_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        recv_proc = subprocess.Popen(
            recv_cmd,
            stdin=send_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        send_proc.stdout.close()  # Allow send_proc to receive SIGPIPE

        recv_stdout, recv_stderr = recv_proc.communicate()
        send_proc.wait()

        return subprocess.CompletedProcess(
            args=ssh_cmd + ["|"] + recv_cmd,
            returncode=recv_proc.returncode,
            stdout=recv_stdout.decode() if recv_stdout else "",
            stderr=recv_stderr.decode() if recv_stderr else "",
        )

    def copy_file(
        self,
        remote_path: str,
        local_path: str,
    ) -> bool:
        """Copy a file from remote server using scp.

        Args:
            remote_path: Remote file path.
            local_path: Local destination path.

        Returns:
            True if successful.
        """
        cmd = ["scp"]
        if self.config.ssh_key:
            cmd.extend(["-i", self.config.ssh_key])
        cmd.extend(["-P", str(self.config.port)])
        cmd.extend(["-o", "BatchMode=yes"])
        cmd.append(f"{self.config.connection_string()}:{remote_path}")
        cmd.append(local_path)

        logger.debug(f"Copying {remote_path} to {local_path}")
        result = subprocess.run(cmd, capture_output=True)
        return result.returncode == 0

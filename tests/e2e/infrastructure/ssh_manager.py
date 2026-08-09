"""
SSH connection management for E2E tests.

Provides functionality to generate SSH keys and establish connections
to test VMs for executing commands and transferring files.
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import paramiko

logger = logging.getLogger(__name__)


@dataclass
class SSHManager:
    """Manages SSH keys and connections for E2E tests."""

    work_dir: Path
    private_key_path: Path | None = None
    public_key_path: Path | None = None
    public_key_content: str | None = None

    def __post_init__(self) -> None:
        """Initialize work directory."""
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def generate_keypair(self) -> tuple[Path, Path]:
        """Generate an ephemeral SSH keypair for testing.

        Returns:
            Tuple of (private_key_path, public_key_path).
        """
        self.private_key_path = self.work_dir / "e2e_test_key"
        self.public_key_path = self.work_dir / "e2e_test_key.pub"

        # Remove existing keys if present
        if self.private_key_path.exists():
            self.private_key_path.unlink()
        if self.public_key_path.exists():
            self.public_key_path.unlink()

        # Generate new keypair
        subprocess.run(
            [
                "ssh-keygen",
                "-t",
                "ed25519",
                "-f",
                str(self.private_key_path),
                "-N",
                "",  # No passphrase
                "-C",
                "e2e-test@znapzend-full",
            ],
            check=True,
            capture_output=True,
        )

        # Set proper permissions
        self.private_key_path.chmod(0o600)

        # Read public key content
        self.public_key_content = self.public_key_path.read_text().strip()

        logger.info(f"Generated SSH keypair: {self.private_key_path}")
        return self.private_key_path, self.public_key_path

    def get_public_key(self) -> str:
        """Get the public key content.

        Returns:
            Public key string for authorized_keys.
        """
        if self.public_key_content is None:
            raise RuntimeError("SSH keypair not generated yet")
        return self.public_key_content

    def connect(
        self,
        host: str,
        user: str = "root",
        port: int = 22,
        timeout: int = 30,
        retries: int = 3,
    ) -> "paramiko.SSHClient":
        """Establish an SSH connection to a host.

        Args:
            host: Hostname or IP address.
            user: SSH username.
            port: SSH port.
            timeout: Connection timeout in seconds.
            retries: Number of connection attempts.

        Returns:
            Connected paramiko SSHClient.

        Raises:
            RuntimeError: If connection fails after all retries.
        """
        import paramiko

        if self.private_key_path is None:
            raise RuntimeError("SSH keypair not generated yet")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        last_error = None
        for attempt in range(retries):
            try:
                logger.debug(f"SSH connection attempt {attempt + 1}/{retries} to {user}@{host}")
                client.connect(
                    hostname=host,
                    port=port,
                    username=user,
                    key_filename=str(self.private_key_path),
                    timeout=timeout,
                    allow_agent=False,
                    look_for_keys=False,
                )
                logger.info(f"SSH connected to {user}@{host}")
                return client
            except Exception as e:
                last_error = e
                logger.debug(f"SSH connection failed: {e}")
                if attempt < retries - 1:
                    time.sleep(5)

        raise RuntimeError(f"SSH connection to {host} failed after {retries} attempts: {last_error}")

    def execute(
        self,
        client: "paramiko.SSHClient",
        command: str,
        timeout: int = 300,
    ) -> tuple[int, str, str]:
        """Execute a command on a remote host.

        Args:
            client: Connected SSH client.
            command: Command to execute.
            timeout: Command timeout in seconds.

        Returns:
            Tuple of (exit_code, stdout, stderr).
        """
        logger.debug(f"Executing: {command}")
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        stdout_str = stdout.read().decode()
        stderr_str = stderr.read().decode()

        if exit_code != 0:
            logger.debug(f"Command failed with exit code {exit_code}: {stderr_str}")

        return exit_code, stdout_str, stderr_str

    def copy_to(
        self,
        client: "paramiko.SSHClient",
        local_path: Path,
        remote_path: str,
    ) -> None:
        """Copy a file to a remote host.

        Args:
            client: Connected SSH client.
            local_path: Local file path.
            remote_path: Remote destination path.
        """
        sftp = client.open_sftp()
        try:
            logger.debug(f"Copying {local_path} to {remote_path}")
            sftp.put(str(local_path), remote_path)
        finally:
            sftp.close()

    def copy_from(
        self,
        client: "paramiko.SSHClient",
        remote_path: str,
        local_path: Path,
    ) -> None:
        """Copy a file from a remote host.

        Args:
            client: Connected SSH client.
            remote_path: Remote file path.
            local_path: Local destination path.
        """
        sftp = client.open_sftp()
        try:
            logger.debug(f"Copying {remote_path} to {local_path}")
            sftp.get(remote_path, str(local_path))
        finally:
            sftp.close()

    def copy_private_key_to_vm(self, client: "paramiko.SSHClient") -> None:
        """Copy the private key to a VM for VM-to-VM SSH.

        This allows the VM to SSH to other VMs in the test environment.

        Args:
            client: Connected SSH client to the destination VM.
        """
        if self.private_key_path is None:
            raise RuntimeError("SSH keypair not generated yet")

        # Create .ssh directory
        self.execute(client, "mkdir -p /root/.ssh && chmod 700 /root/.ssh")

        # Copy private key
        self.copy_to(client, self.private_key_path, "/root/.ssh/id_e2e")

        # Set permissions
        self.execute(client, "chmod 600 /root/.ssh/id_e2e")

        # Configure SSH to use this key and disable host key checking for tests
        ssh_config = """
Host *
    IdentityFile /root/.ssh/id_e2e
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
"""
        self.execute(client, f"cat > /root/.ssh/config << 'EOF'\n{ssh_config}\nEOF")
        self.execute(client, "chmod 600 /root/.ssh/config")

        logger.info("Copied private key to VM for inter-VM SSH")

    def close(self, client: "paramiko.SSHClient") -> None:
        """Close an SSH connection.

        Args:
            client: SSH client to close.
        """
        try:
            client.close()
        except Exception:
            pass

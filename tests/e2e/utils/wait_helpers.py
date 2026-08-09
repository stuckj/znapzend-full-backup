"""
Wait helpers for E2E tests.

Provides utilities for waiting on VM readiness and service availability.
"""

from __future__ import annotations

import logging
import socket
import time
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    import paramiko

logger = logging.getLogger(__name__)


def wait_for_ssh(
    host: str,
    port: int = 22,
    timeout: int = 300,
    interval: int = 5,
) -> bool:
    """Wait for SSH port to become available.

    Args:
        host: Hostname or IP address.
        port: SSH port number.
        timeout: Maximum seconds to wait.
        interval: Seconds between attempts.

    Returns:
        True if SSH is available, False if timeout.
    """
    logger.debug(f"Waiting for SSH on {host}:{port}...")
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, port))
            sock.close()
            logger.info(f"SSH available on {host}:{port}")
            return True
        except (socket.error, socket.timeout, OSError):
            logger.debug(f"SSH not yet available on {host}:{port}, retrying...")
            time.sleep(interval)

    logger.warning(f"Timeout waiting for SSH on {host}:{port}")
    return False


def wait_for_file(
    ssh_client: "paramiko.SSHClient",
    path: str,
    timeout: int = 300,
    interval: int = 5,
) -> bool:
    """Wait for a file to exist on a remote host.

    Args:
        ssh_client: Connected SSH client.
        path: Path to the file to check.
        timeout: Maximum seconds to wait.
        interval: Seconds between attempts.

    Returns:
        True if file exists, False if timeout.
    """
    logger.debug(f"Waiting for file {path}...")
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            _, stdout, _ = ssh_client.exec_command(f"test -f {path} && echo yes || echo no")
            result = stdout.read().decode().strip()
            if result == "yes":
                logger.info(f"File {path} exists")
                return True
        except Exception as e:
            logger.debug(f"Error checking file: {e}")

        time.sleep(interval)

    logger.warning(f"Timeout waiting for file {path}")
    return False


def wait_for_zpool(
    ssh_client: "paramiko.SSHClient",
    pool_name: str,
    timeout: int = 300,
    interval: int = 5,
) -> bool:
    """Wait for a ZFS pool to be online.

    Args:
        ssh_client: Connected SSH client.
        pool_name: Name of the ZFS pool.
        timeout: Maximum seconds to wait.
        interval: Seconds between attempts.

    Returns:
        True if pool is online, False if timeout.
    """
    logger.debug(f"Waiting for zpool {pool_name}...")
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            _, stdout, stderr = ssh_client.exec_command(
                f"zpool list -H -o health {pool_name} 2>/dev/null"
            )
            health = stdout.read().decode().strip()
            if health == "ONLINE":
                logger.info(f"Pool {pool_name} is ONLINE")
                return True
            elif health:
                logger.debug(f"Pool {pool_name} health: {health}")
        except Exception as e:
            logger.debug(f"Error checking pool: {e}")

        time.sleep(interval)

    logger.warning(f"Timeout waiting for pool {pool_name}")
    return False


def wait_for_command(
    ssh_client: "paramiko.SSHClient",
    command: str,
    expected_output: str | None = None,
    expected_exit_code: int = 0,
    timeout: int = 300,
    interval: int = 5,
) -> bool:
    """Wait for a command to succeed or produce expected output.

    Args:
        ssh_client: Connected SSH client.
        command: Command to execute.
        expected_output: Optional string that must be in stdout.
        expected_exit_code: Expected exit code.
        timeout: Maximum seconds to wait.
        interval: Seconds between attempts.

    Returns:
        True if command succeeds as expected, False if timeout.
    """
    logger.debug(f"Waiting for command: {command}")
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            _, stdout, stderr = ssh_client.exec_command(command)
            exit_code = stdout.channel.recv_exit_status()
            output = stdout.read().decode()

            if exit_code == expected_exit_code:
                if expected_output is None or expected_output in output:
                    logger.info(f"Command succeeded: {command}")
                    return True
        except Exception as e:
            logger.debug(f"Command error: {e}")

        time.sleep(interval)

    logger.warning(f"Timeout waiting for command: {command}")
    return False


def wait_with_retry(
    func: Callable[[], bool],
    timeout: int = 300,
    interval: int = 5,
    description: str = "condition",
) -> bool:
    """Generic retry wrapper for a boolean function.

    Args:
        func: Function that returns True on success.
        timeout: Maximum seconds to wait.
        interval: Seconds between attempts.
        description: Description for logging.

    Returns:
        True if function succeeded, False if timeout.
    """
    logger.debug(f"Waiting for {description}...")
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            if func():
                logger.info(f"Condition met: {description}")
                return True
        except Exception as e:
            logger.debug(f"Error in {description}: {e}")

        time.sleep(interval)

    logger.warning(f"Timeout waiting for {description}")
    return False


def wait_for_cloud_init(
    ssh_client: "paramiko.SSHClient",
    timeout: int = 600,
    interval: int = 10,
) -> bool:
    """Wait for cloud-init to complete.

    Checks both the cloud-init status command and the e2e-ready marker file.

    Args:
        ssh_client: Connected SSH client.
        timeout: Maximum seconds to wait.
        interval: Seconds between attempts.

    Returns:
        True if cloud-init completed, False if timeout.
    """
    logger.debug("Waiting for cloud-init to complete...")
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            # Check cloud-init status
            _, stdout, _ = ssh_client.exec_command("cloud-init status 2>/dev/null || echo unknown")
            status = stdout.read().decode().strip()

            if "done" in status:
                # Also check for our ready marker
                _, stdout, _ = ssh_client.exec_command(
                    "test -f /var/run/e2e-ready && echo yes || echo no"
                )
                if stdout.read().decode().strip() == "yes":
                    logger.info("Cloud-init completed and e2e-ready marker found")
                    return True

            logger.debug(f"Cloud-init status: {status}")

        except Exception as e:
            logger.debug(f"Error checking cloud-init: {e}")

        time.sleep(interval)

    logger.warning("Timeout waiting for cloud-init")
    return False

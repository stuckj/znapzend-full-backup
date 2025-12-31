"""
Base image building for E2E tests.

Provides functionality to download and customize Ubuntu cloud images
with ZFS support for E2E testing.
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlretrieve

logger = logging.getLogger(__name__)


@dataclass
class ImageBuilder:
    """Builds and caches base images for E2E test VMs."""

    cache_dir: Path
    ubuntu_version: str = "noble"  # 24.04 LTS

    # Ubuntu cloud image URL
    UBUNTU_BASE_URL: str = "https://cloud-images.ubuntu.com"

    def __post_init__(self) -> None:
        """Initialize cache directory."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_image_url(self) -> str:
        """Get the Ubuntu cloud image download URL."""
        return (
            f"{self.UBUNTU_BASE_URL}/{self.ubuntu_version}/current/"
            f"{self.ubuntu_version}-server-cloudimg-amd64.img"
        )

    @property
    def base_image_path(self) -> Path:
        """Path to the downloaded base image."""
        return self.cache_dir / f"ubuntu-{self.ubuntu_version}-base.qcow2"

    @property
    def test_image_path(self) -> Path:
        """Path to the customized test image."""
        return self.cache_dir / "znapzend-full-test.qcow2"

    def download_base_image(self, force: bool = False) -> Path:
        """Download the Ubuntu cloud image.

        Args:
            force: Re-download even if cached.

        Returns:
            Path to the downloaded image.
        """
        if self.base_image_path.exists() and not force:
            logger.info(f"Using cached base image: {self.base_image_path}")
            return self.base_image_path

        logger.info(f"Downloading Ubuntu {self.ubuntu_version} cloud image...")
        tmp_path = self.cache_dir / "download.tmp"

        try:
            urlretrieve(self.base_image_url, tmp_path)
            tmp_path.rename(self.base_image_path)
            logger.info(f"Downloaded base image: {self.base_image_path}")
        except Exception as e:
            if tmp_path.exists():
                tmp_path.unlink()
            raise RuntimeError(f"Failed to download base image: {e}")

        return self.base_image_path

    def build_test_image(self, force_rebuild: bool = False) -> Path:
        """Build the customized test image with ZFS and dependencies.

        Args:
            force_rebuild: Rebuild even if cached.

        Returns:
            Path to the test image.
        """
        # Check if we can use cached image
        if self.test_image_path.exists() and not force_rebuild:
            # Verify image is valid
            if self.verify_image(self.test_image_path):
                logger.info(f"Using cached test image: {self.test_image_path}")
                return self.test_image_path
            else:
                logger.warning("Cached test image is invalid, rebuilding...")

        # Ensure base image exists
        self.download_base_image()

        # Build using external script if available, otherwise use virt-customize
        script_path = Path(__file__).parent.parent / "images" / "build_base_image.sh"
        if script_path.exists():
            return self._build_with_script(script_path)
        else:
            return self._build_with_virt_customize()

    def _build_with_script(self, script_path: Path) -> Path:
        """Build image using the shell script."""
        logger.info("Building test image using build script...")

        env = os.environ.copy()
        env["CACHE_DIR"] = str(self.cache_dir)

        result = subprocess.run(
            ["bash", str(script_path)],
            env=env,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.error(f"Build script failed: {result.stderr}")
            raise RuntimeError(f"Image build failed: {result.stderr}")

        logger.info(f"Test image built: {self.test_image_path}")
        return self.test_image_path

    def _build_with_virt_customize(self) -> Path:
        """Build image using virt-customize."""
        logger.info("Building test image using virt-customize...")

        # Create a copy of the base image
        tmp_image = self.cache_dir / "build.tmp.qcow2"
        subprocess.run(
            ["qemu-img", "create", "-f", "qcow2", "-F", "qcow2",
             "-b", str(self.base_image_path), str(tmp_image), "20G"],
            check=True,
            capture_output=True,
        )

        try:
            # Customize the image
            customize_cmd = [
                "virt-customize",
                "-a", str(tmp_image),
                "--run-command", "apt-get update",
                "--install", "zfsutils-linux,sgdisk,python3-pip,python3-yaml,openssh-server",
                "--run-command", "apt-get clean",
                "--run-command", "rm -rf /var/lib/apt/lists/*",
                # Enable SSH root login
                "--write", "/etc/ssh/sshd_config.d/99-e2e.conf:PermitRootLogin yes\nPasswordAuthentication no\n",
                # Tune ZFS for small VMs
                "--write", "/etc/modprobe.d/zfs.conf:options zfs zfs_arc_max=536870912\n",
            ]

            subprocess.run(customize_cmd, check=True, capture_output=True)

            # Convert and compress
            subprocess.run(
                ["qemu-img", "convert", "-O", "qcow2", "-c",
                 str(tmp_image), str(self.test_image_path)],
                check=True,
                capture_output=True,
            )

            logger.info(f"Test image built: {self.test_image_path}")
            return self.test_image_path

        finally:
            if tmp_image.exists():
                tmp_image.unlink()

    def verify_image(self, image_path: Path) -> bool:
        """Verify that an image is valid.

        Args:
            image_path: Path to the image to verify.

        Returns:
            True if image is valid.
        """
        if not image_path.exists():
            return False

        try:
            result = subprocess.run(
                ["qemu-img", "check", str(image_path)],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_image_info(self, image_path: Path) -> dict:
        """Get information about an image.

        Args:
            image_path: Path to the image.

        Returns:
            Dict with image information.
        """
        result = subprocess.run(
            ["qemu-img", "info", "--output=json", str(image_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        import json
        return json.loads(result.stdout)

    def compute_checksum(self, image_path: Path) -> str:
        """Compute SHA256 checksum of an image.

        Args:
            image_path: Path to the image.

        Returns:
            SHA256 hex digest.
        """
        sha256 = hashlib.sha256()
        with open(image_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

#!/bin/bash
#
# Build base test image for znapzend-full E2E tests
#
# This script:
# 1. Downloads Ubuntu 24.04 cloud image
# 2. Expands the image to allow ZFS operations
# 3. Optionally pre-installs packages (if virt-customize works)
#
# The image is designed to work with cloud-init which handles
# most configuration at boot time.
#
# Requirements:
# - qemu-img
# - curl or wget
# - Optionally: virt-customize (from libguestfs-tools) for pre-caching packages
#
# Usage:
#   ./build_base_image.sh [--force]
#
# Environment variables:
#   CACHE_DIR - Directory for caching images (default: ~/.cache/znapzend-full-e2e)
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE_DIR="${CACHE_DIR:-$HOME/.cache/znapzend-full-e2e}"
UBUNTU_VERSION="noble"
UBUNTU_URL="https://cloud-images.ubuntu.com/${UBUNTU_VERSION}/current/${UBUNTU_VERSION}-server-cloudimg-amd64.img"
BASE_IMAGE="${CACHE_DIR}/ubuntu-${UBUNTU_VERSION}-base.qcow2"
TEST_IMAGE="${CACHE_DIR}/znapzend-full-test.qcow2"

FORCE_REBUILD=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --force|-f)
            FORCE_REBUILD=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--force]"
            echo ""
            echo "Build base test image for znapzend-full E2E tests."
            echo ""
            echo "Options:"
            echo "  --force, -f    Force rebuild even if image exists"
            echo "  --help, -h     Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check for required tools
check_tool() {
    if ! command -v "$1" &>/dev/null; then
        echo "ERROR: Required tool '$1' not found"
        echo "Please install: $2"
        exit 1
    fi
}

check_tool qemu-img "qemu-utils"
check_tool curl "curl"

# Create cache directory
mkdir -p "$CACHE_DIR"

# Download base image if not cached
download_base_image() {
    if [[ -f "$BASE_IMAGE" ]] && [[ "$FORCE_REBUILD" != "true" ]]; then
        echo "Using cached base image: $BASE_IMAGE"
        return 0
    fi

    echo "Downloading Ubuntu ${UBUNTU_VERSION} cloud image..."
    curl -L --progress-bar -o "${BASE_IMAGE}.tmp" "$UBUNTU_URL"
    mv "${BASE_IMAGE}.tmp" "$BASE_IMAGE"
    echo "Downloaded base image: $BASE_IMAGE"
}

# Check if rebuild is needed
needs_rebuild() {
    if [[ "$FORCE_REBUILD" == "true" ]]; then
        return 0
    fi

    if [[ ! -f "$TEST_IMAGE" ]]; then
        return 0
    fi

    # Check if test image is newer than base
    if [[ "$BASE_IMAGE" -nt "$TEST_IMAGE" ]]; then
        return 0
    fi

    # Verify image is valid
    if ! qemu-img check "$TEST_IMAGE" &>/dev/null; then
        return 0
    fi

    echo "Using cached test image: $TEST_IMAGE"
    return 1
}

# Try to pre-install packages with virt-customize (optional optimization)
try_preinstall_packages() {
    if ! command -v virt-customize &>/dev/null; then
        echo "virt-customize not found, skipping package pre-installation"
        echo "Packages will be installed via cloud-init at boot time"
        return 1
    fi

    echo "Attempting to pre-install packages with virt-customize..."
    echo "(This speeds up VM boot but is optional - cloud-init will install packages if this fails)"

    local tmp_image="${CACHE_DIR}/build.tmp.qcow2"
    cp "$BASE_IMAGE" "$tmp_image"
    qemu-img resize "$tmp_image" 20G

    # Try virt-customize - may fail due to networking issues on some systems
    if virt-customize -a "$tmp_image" \
        --run-command "apt-get update" \
        --install "zfsutils-linux,sgdisk,python3-pip,python3-yaml,openssh-server,curl" \
        --run-command "apt-get clean" \
        --run-command "rm -rf /var/lib/apt/lists/*" \
        --write "/etc/ssh/sshd_config.d/99-e2e.conf:PermitRootLogin yes
PasswordAuthentication no
" \
        --write "/etc/modprobe.d/zfs.conf:options zfs zfs_arc_max=536870912
" \
        --run-command "systemctl enable ssh" 2>&1; then

        # Success - compact and save
        qemu-img convert -O qcow2 -c "$tmp_image" "$TEST_IMAGE"
        rm -f "$tmp_image"
        echo "Successfully pre-installed packages"
        return 0
    else
        echo "virt-customize failed (this is OK - cloud-init will handle package installation)"
        rm -f "$tmp_image"
        return 1
    fi
}

# Build minimal image (just resize, no package pre-installation)
build_minimal_image() {
    echo "Building minimal test image (packages will be installed via cloud-init)..."

    # Just copy and resize the base image
    cp "$BASE_IMAGE" "$TEST_IMAGE"
    qemu-img resize "$TEST_IMAGE" 20G

    echo "Minimal test image built: $TEST_IMAGE"
}

# Main execution
download_base_image

if needs_rebuild; then
    # Try to pre-install packages, fall back to minimal image
    if ! try_preinstall_packages; then
        build_minimal_image
    fi
fi

# Print image info
echo ""
echo "Image information:"
qemu-img info "$TEST_IMAGE"
echo ""
echo "Image ready: $TEST_IMAGE"

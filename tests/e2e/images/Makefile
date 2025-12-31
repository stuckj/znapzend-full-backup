# Makefile for E2E test image management
#
# Usage:
#   make image       - Build test image (uses cache if available)
#   make force       - Force rebuild of test image
#   make verify      - Verify test image integrity
#   make clean       - Remove test image
#   make clean-all   - Remove all cached images
#   make info        - Show image information
#

CACHE_DIR ?= $(HOME)/.cache/znapzend-full-e2e
TEST_IMAGE := $(CACHE_DIR)/znapzend-full-test.qcow2
BASE_IMAGE := $(CACHE_DIR)/ubuntu-noble-base.qcow2

.PHONY: all image force verify clean clean-all info help

all: image

# Build test image (uses cache)
image:
	@echo "Building E2E test image..."
	@./build_base_image.sh
	@echo "Done."

# Force rebuild
force:
	@echo "Force rebuilding E2E test image..."
	@./build_base_image.sh --force
	@echo "Done."

# Verify image integrity
verify:
	@if [ -f "$(TEST_IMAGE)" ]; then \
		echo "Verifying $(TEST_IMAGE)..."; \
		qemu-img check "$(TEST_IMAGE)" && echo "Image OK"; \
	else \
		echo "Test image not found: $(TEST_IMAGE)"; \
		exit 1; \
	fi

# Show image information
info:
	@if [ -f "$(TEST_IMAGE)" ]; then \
		echo "Test image: $(TEST_IMAGE)"; \
		qemu-img info "$(TEST_IMAGE)"; \
	else \
		echo "Test image not found"; \
	fi
	@echo ""
	@if [ -f "$(BASE_IMAGE)" ]; then \
		echo "Base image: $(BASE_IMAGE)"; \
		qemu-img info "$(BASE_IMAGE)"; \
	else \
		echo "Base image not found"; \
	fi

# Remove test image only
clean:
	@echo "Removing test image..."
	@rm -f "$(TEST_IMAGE)"
	@echo "Done."

# Remove all cached images
clean-all:
	@echo "Removing all cached images..."
	@rm -rf "$(CACHE_DIR)"
	@echo "Done."

# Show help
help:
	@echo "E2E Test Image Management"
	@echo ""
	@echo "Targets:"
	@echo "  image      Build test image (uses cache if available)"
	@echo "  force      Force rebuild of test image"
	@echo "  verify     Verify test image integrity"
	@echo "  info       Show image information"
	@echo "  clean      Remove test image"
	@echo "  clean-all  Remove all cached images"
	@echo "  help       Show this help"
	@echo ""
	@echo "Environment:"
	@echo "  CACHE_DIR  Image cache directory (default: ~/.cache/znapzend-full-e2e)"

#!/bin/bash
#
# Download and install noVNC static files into the Flask app.
# Run this once during project setup.
#

set -e

NOVNC_VERSION="1.5.0"
DEST_DIR="app/static/novnc"

echo "Downloading noVNC v${NOVNC_VERSION}..."

# Clean previous install
rm -rf "$DEST_DIR"
mkdir -p "$DEST_DIR"

# Download and extract
curl -L "https://github.com/novnc/noVNC/archive/refs/tags/v${NOVNC_VERSION}.tar.gz" | tar xz

# Copy only what we need (core library + vendor deps)
cp -r "noVNC-${NOVNC_VERSION}/core" "$DEST_DIR/core"
cp -r "noVNC-${NOVNC_VERSION}/vendor" "$DEST_DIR/vendor"

# Clean up
rm -rf "noVNC-${NOVNC_VERSION}"

echo "noVNC v${NOVNC_VERSION} installed to ${DEST_DIR}/"
echo "Files:"
ls -la "$DEST_DIR/core/"

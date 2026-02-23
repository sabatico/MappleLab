#!/bin/bash
# Setup local Docker registry for TART VM storage.
# Run this on the central registry/Flask machine.

set -e

REGISTRY_DATA_DIR="${REGISTRY_DATA_DIR:-./tart-registry}"

echo "Creating registry data directory: $REGISTRY_DATA_DIR"
sudo mkdir -p "$REGISTRY_DATA_DIR"

echo "Pulling registry:2 image..."
docker pull registry:2

echo "Starting registry container..."
docker run -d \
  -p 5001:5000 \
  -v "$REGISTRY_DATA_DIR:/var/lib/registry" \
  -e REGISTRY_STORAGE_DELETE_ENABLED=true \
  --restart always \
  --name tart-registry \
  registry:2

echo ""
echo "Registry is running at http://localhost:5001"
echo "Test with: curl http://localhost:5001/v2/"
echo "Delete API enabled: REGISTRY_STORAGE_DELETE_ENABLED=true"
echo ""
echo "Set REGISTRY_URL=<this-machine-ip>:5001 in your .env file."

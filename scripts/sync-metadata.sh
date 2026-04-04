#!/bin/bash
# Synchronize external metadata repository with local copy

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
METADATA_DIR="${FAIGATE_METADATA_DIR:-$HOME/.faigate/metadata}"
LOG_FILE="/tmp/faigate-metadata-sync.log"

echo "$(date): Starting metadata synchronization" >> "$LOG_FILE"

cd "$METADATA_DIR" || {
    echo "ERROR: Metadata directory not found: $METADATA_DIR" >> "$LOG_FILE"
    exit 1
}

# Check if git is available
if ! command -v git &> /dev/null; then
    echo "ERROR: git not found" >> "$LOG_FILE"
    exit 1
fi

# Pull latest changes
echo "Pulling latest metadata from repository..." >> "$LOG_FILE"
if git pull origin main 2>&1 | tee -a "$LOG_FILE"; then
    echo "$(date): Successfully updated metadata repository" >> "$LOG_FILE"
    echo "Metadata updated successfully."

    # Optionally touch the catalog file to ensure mtime changes
    # This ensures Gate picks up changes even if file content identical but metadata updated
    if [ -f "providers/catalog.v1.json" ]; then
        touch "providers/catalog.v1.json"
        echo "Touched catalog file to update mtime" >> "$LOG_FILE"
    fi
    if [ -f "products/gate/overlays.v1.json" ]; then
        touch "products/gate/overlays.v1.json"
        echo "Touched overlay file to update mtime" >> "$LOG_FILE"
    fi
    if [ -f "offerings/catalog.v1.json" ]; then
        touch "offerings/catalog.v1.json"
        echo "Touched offerings catalog file to update mtime" >> "$LOG_FILE"
    fi
    if [ -f "packages/catalog.v1.json" ]; then
        touch "packages/catalog.v1.json"
        echo "Touched packages catalog file to update mtime" >> "$LOG_FILE"
    fi
else
    echo "$(date): Failed to update metadata repository" >> "$LOG_FILE"
    echo "ERROR: git pull failed" >> "$LOG_FILE"
    exit 1
fi

echo "$(date): Synchronization completed" >> "$LOG_FILE"
exit 0

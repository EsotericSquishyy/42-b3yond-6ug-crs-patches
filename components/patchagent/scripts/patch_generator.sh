#!/bin/bash -eu

if [ -n "${AIXCC_MOCK_MODE:-}" ]; then
    echo "[-] Starting the MockServer component..."
    python -m patch_generator.mock
else
    echo "[-] Starting the Docker service..."
    start-docker.sh
    echo "[-] Docker service started."
    docker ps || { echo "[-] Docker is not running. Exiting..."; exit 1; }

    echo "[-] Cleaning up workspace..."
    rm -rf /patch_generator

    echo "[-] Starting the Patch Daemon..."
    python -m patch_generator.main
fi

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_TAG="filterama/windows-builder:latest"

echo "[1/3] Building Docker image ${IMAGE_TAG} ..."
docker build -f "${SCRIPT_DIR}/docker/windows/Dockerfile" -t "${IMAGE_TAG}" "${SCRIPT_DIR}"

echo "[2/3] Building Windows executable with PyInstaller ..."
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "${SCRIPT_DIR}:/src" \
  -w /src \
  "${IMAGE_TAG}" \
  /entrypoint-windows.sh pyinstaller \
    --noconfirm \
    --clean \
    --windowed \
    --name Filterama \
    --hidden-import matplotlib.backends.backend_qtagg \
    --collect-submodules matplotlib.backends \
    --collect-all pyckles \
    --add-data "Resources;Resources" \
    src/Filterama.py

echo "[3/3] Done. Result: dist/Filterama/Filterama.exe"

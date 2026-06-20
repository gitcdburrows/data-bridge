#!/usr/bin/env bash
# Build the Bloomberg Data Bridge into a single executable.
#
# Note: PyInstaller is not a cross-compiler — run this on the OS you want to
# target. For the production Windows workstation use scripts/build.ps1. This
# script is handy for building/smoke-testing the app on macOS or Linux.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  python -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip
# --extra-index-url lets pip resolve blpapi from Bloomberg while everything
# else comes from PyPI. (blpapi only ships wheels for some platforms.)
pip install --extra-index-url=https://blpapi.bloomberg.com/repository/releases/python/simple/ -r requirements-dev.txt

pyinstaller --clean --noconfirm data_bridge.spec

echo
echo "Built dist/BloombergBridge"

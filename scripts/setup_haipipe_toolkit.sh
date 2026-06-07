#!/usr/bin/env bash
set -euo pipefail

git submodule update --init --recursive external/haipipe-toolkit
python -m pip install -e external/haipipe-toolkit

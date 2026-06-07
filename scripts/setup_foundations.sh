#!/usr/bin/env bash
set -euo pipefail

git submodule update --init --recursive external/haipipe-toolkit external/tools external/codex-oauth external/academic-research-skills
python -m pip install -e external/codex-oauth

cat <<'MSG'
Optional heavy install for real haipipe/WellDoc loaders:
  python -m pip install -e external/haipipe-toolkit
MSG

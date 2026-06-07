$ErrorActionPreference = "Stop"

git submodule update --init --recursive external/haipipe-toolkit external/tools external/codex-oauth external/academic-research-skills
python -m pip install -e external/codex-oauth

Write-Host "Optional heavy install for real haipipe/WellDoc loaders:"
Write-Host "  python -m pip install -e external/haipipe-toolkit"

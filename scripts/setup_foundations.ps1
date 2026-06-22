$ErrorActionPreference = "Stop"

git submodule update --init --recursive external/haipipe-toolkit external/tools external/codex-oauth external/academic-research-skills external/cdhai-hapf
python -m pip install -e external/codex-oauth

Write-Host "Optional heavy install for real haipipe/WellDoc loaders:"
Write-Host "  python -m pip install -e external/haipipe-toolkit"
Write-Host "Optional HAPF install for personalized forecasting tasks:"
Write-Host "  python -m pip install -e external/cdhai-hapf"

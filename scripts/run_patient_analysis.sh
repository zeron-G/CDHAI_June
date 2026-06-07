#!/usr/bin/env bash
set -euo pipefail

INPUT_PATH="${1:-examples/sample_patient.csv}"
PATIENT_ID="${2:-demo}"
CYCLES="${3:-5}"
LLM_PROVIDER="${4:-mock}"
CONFIG_PATH="${5:-configs/default.yaml}"

python -m cdhai_june run \
  --input "$INPUT_PATH" \
  --patient-id "$PATIENT_ID" \
  --cycles "$CYCLES" \
  --llm-provider "$LLM_PROVIDER" \
  --config "$CONFIG_PATH"

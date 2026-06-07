param(
    [string]$InputPath = "examples/sample_patient.csv",
    [string]$PatientId = "demo",
    [int]$Cycles = 5,
    [string]$LlmProvider = "mock",
    [string]$ConfigPath = "configs/default.yaml"
)

$ErrorActionPreference = "Stop"
python -m cdhai_june run `
    --input $InputPath `
    --patient-id $PatientId `
    --cycles $Cycles `
    --llm-provider $LlmProvider `
    --config $ConfigPath

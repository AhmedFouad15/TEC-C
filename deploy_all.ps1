# Tec-C Multi-Chain Deploy All (PowerShell)
$Root = $PSScriptRoot
$VenvPy = Join-Path $Root "agent\.venv\Scripts\python.exe"
$Script = Join-Path $Root "deploy_all_chains.py"

if (Test-Path $VenvPy) {
    & $VenvPy $Script $args
} else {
    python $Script $args
}

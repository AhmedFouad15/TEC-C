# Tec-C Automated Wallet Setup & Environment Wizard (PowerShell)
$Root = $PSScriptRoot
$VenvPy = Join-Path $Root "agent\.venv\Scripts\python.exe"
$Script = Join-Path $Root "setup_wallet_env.py"

if (Test-Path $VenvPy) {
    & $VenvPy $Script $args
} else {
    python $Script $args
}

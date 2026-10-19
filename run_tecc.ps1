# Tec-C One-Click Launcher (PowerShell)
$Root = $PSScriptRoot
$VenvPy = Join-Path $Root "agent\.venv\Scripts\python.exe"
$Script = Join-Path $Root "run_tecc.py"

if (Test-Path $VenvPy) {
    & $VenvPy $Script $args
} else {
    python $Script $args
}

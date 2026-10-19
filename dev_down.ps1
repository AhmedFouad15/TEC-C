# Stop what dev_up.ps1 started (Anvil keeps its state in agent\.state\anvil-state.json for the next run).
# Run:  powershell -ExecutionPolicy Bypass -File .\dev_down.ps1
$State = Join-Path $PSScriptRoot 'agent\.state'
$Pids  = Join-Path $State 'dev_pids.json'

if (Test-Path $Pids) {
    (Get-Content $Pids -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object {
        Stop-Process -Id $_.Value -Force -ErrorAction SilentlyContinue
        Write-Host "> stopped $($_.Name) (pid $($_.Value))"
    }
    Remove-Item $Pids -Force
}
# anything still listening on the stack's ports (e.g. started before the pid file existed)
foreach ($port in 8545, 8000, 8001, 5500) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "> stopped the listener on port $port"
    }
}
Write-Host '> Tec-C stack stopped.'

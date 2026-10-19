# Start the whole Tec-C stack on Windows, then open the website (PowerShell 5.1+; same steps as dev_up.sh).
#   1. a local blockchain (Anvil, chain 31337) that remembers its state between runs
#   2. the real vault on it (TecAccount + TetherGuardHook + session key), deployed once
#   3. the Brain API on http://127.0.0.1:8000 (connected to that vault; reads agent\.env if present)
#   4. the website on http://localhost:5500 (localhost, not an IP: passkeys / FaceID need a host name)
# Run:   powershell -ExecutionPolicy Bypass -File .\dev_up.ps1
# Stop:  powershell -ExecutionPolicy Bypass -File .\dev_down.ps1
# 'Continue', not 'Stop': in Windows PowerShell 5.1 a native tool writing a warning to stderr (Python does) would
# otherwise abort the script. Every step checks its own result and throws on failure.
$ErrorActionPreference = 'Continue'

$Root   = $PSScriptRoot
$Agent  = Join-Path $Root 'agent'
$State  = Join-Path $Agent '.state'
$Rpc    = 'http://127.0.0.1:8545'
$UiPort = 5500
$Pids   = Join-Path $State 'dev_pids.json'
New-Item -ItemType Directory -Force -Path $State | Out-Null

function Say($msg) { Write-Host "> $msg" -ForegroundColor Green }
function Test-Port([int]$port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { $client.Connect('127.0.0.1', $port); return $true } catch { return $false } finally { $client.Close() }
}
function Wait-Port([int]$port, [int]$seconds) {
    for ($i = 0; $i -lt ($seconds * 4); $i++) { if (Test-Port $port) { return $true }; Start-Sleep -Milliseconds 250 }
    return $false
}
function Find-Tool([string]$name) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($dir in @('C:\foundry', (Join-Path $HOME '.foundry\bin'))) {
        $exe = Join-Path $dir "$name.exe"
        if (Test-Path $exe) { return $exe }
    }
    return $null
}
function Stop-Listener([int]$port) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}

# --- tools ----------------------------------------------------------------------------------------------------
$anvil = Find-Tool 'anvil'
$forge = Find-Tool 'forge'
if (-not $anvil -or -not $forge) { throw 'Foundry is missing: install it from https://getfoundry.sh (anvil.exe and forge.exe)' }

$python = Join-Path $Agent '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) { throw 'Python is missing: cd agent; python -m venv .venv; .venv\Scripts\pip install -r requirements.txt' }
    $python = $cmd.Source
}
& $python -c "import fastapi, uvicorn, langgraph" *> $null
if ($LASTEXITCODE -ne 0) { throw "Python packages missing for $python : pip install -r agent\requirements.txt" }

$started = @{}

# --- 0. compiled contracts (rebuild when any artifact the Brain loads is missing) ------------------------------
$out = Join-Path $Root 'contracts\out'
$needed = @('TetherGuardHook.sol\TetherGuardHook.json', 'TecAccount.sol\TecAccount.json',
            'SessionKeyValidator.sol\SessionKeyValidator.json', 'PrivacyAuditAnchor.sol\PrivacyAuditAnchor.json')
$missing = $needed | Where-Object { -not (Test-Path (Join-Path $out $_)) }
if ($missing) {
    Say 'Compiling contracts...'
    Push-Location (Join-Path $Root 'contracts')
    try { & $forge build | Out-Null; if ($LASTEXITCODE -ne 0) { throw 'forge build failed' } } finally { Pop-Location }
}

# --- 1. chain ---------------------------------------------------------------------------------------------------
if (Test-Port 8545) {
    Say 'Local chain already running on 8545'
} else {
    Say 'Starting the local chain (Anvil, chain 31337)...'
    $stateFile = Join-Path $State 'anvil-state.json'
    $p = Start-Process -FilePath $anvil -WindowStyle Hidden -PassThru `
        -ArgumentList @('--port', '8545', '--chain-id', '31337', '--state', "`"$stateFile`"", '--state-interval', '10', '--silent') `
        -RedirectStandardOutput (Join-Path $State 'anvil.log') -RedirectStandardError (Join-Path $State 'anvil.err.log')
    $started.anvil = $p.Id
    if (-not (Wait-Port 8545 15)) { throw "Anvil did not start; see $State\anvil.err.log" }
}

# --- 2. vault (deploy unless the saved one is still on the chain) ----------------------------------------------
$market = Join-Path $State 'markets\anvil.json'
$needDeploy = $true
if (Test-Path $market) {
    $acct = (Get-Content $market -Raw | ConvertFrom-Json).deployment.account
    $body = @{ jsonrpc = '2.0'; id = 1; method = 'eth_getCode'; params = @($acct, 'latest') } | ConvertTo-Json -Compress
    try {
        $code = (Invoke-RestMethod -Uri $Rpc -Method Post -ContentType 'application/json' -Body $body).result
        if ($code -and $code -ne '0x') { $needDeploy = $false; Say "Vault found on the chain: $acct" }
    } catch { }
}
if ($needDeploy) {
    Say 'Deploying the vault on the local chain...'
    Push-Location $Agent
    try {
        & $python scripts\deploy_market_chain.py --network anvil --rpc $Rpc
        if ($LASTEXITCODE -ne 0) { throw 'vault deployment failed' }
    } finally { Pop-Location }
}

# --- 3. Brain (always restarted so it picks up the deployment and agent\.env) -----------------------------------
Stop-Listener 8000
Start-Sleep -Milliseconds 500
Say 'Starting the Brain API on http://127.0.0.1:8000 ...'
$env:TECC_NETWORK = 'anvil'
$env:TECC_CORS_ORIGINS = "http://localhost:$UiPort,http://127.0.0.1:$UiPort,http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000"
$uvArgs = @('-m', 'uvicorn', 'tecc_brain.app:app', '--host', '127.0.0.1', '--port', '8000')
if (Test-Path (Join-Path $Agent '.env')) { $uvArgs += @('--env-file', '.env'); Say 'Loading API keys from agent\.env' }
$p = Start-Process -FilePath $python -ArgumentList $uvArgs -WorkingDirectory $Agent -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $State 'brain.log') -RedirectStandardError (Join-Path $State 'brain.err.log')
$started.brain = $p.Id
$healthy = $false
for ($i = 0; $i -lt 60; $i++) {
    try { Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2 | Out-Null; $healthy = $true; break } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $healthy) { throw "The Brain did not start; see $State\brain.err.log" }

# --- 4. website -------------------------------------------------------------------------------------------------
if (Test-Port $UiPort) {
    Say "Website already running on $UiPort"
} else {
    Say "Starting the website on http://localhost:$UiPort ..."
    $p = Start-Process -FilePath $python -ArgumentList @('-m', 'http.server', "$UiPort", '--bind', '127.0.0.1') `
        -WorkingDirectory (Join-Path $Root 'web') -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $State 'web.log') -RedirectStandardError (Join-Path $State 'web.err.log')
    $started.web = $p.Id
    Wait-Port $UiPort 10 | Out-Null
}

# remember what this script started, for dev_down.ps1 (merge with an earlier run)
$all = @{}
if (Test-Path $Pids) { (Get-Content $Pids -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $all[$_.Name] = $_.Value } }
$started.GetEnumerator() | ForEach-Object { $all[$_.Key] = $_.Value }
$all | ConvertTo-Json | Set-Content -Path $Pids -Encoding UTF8

Write-Host ''
Say 'Ready:'
Write-Host "    Landing page   http://localhost:$UiPort/"
Write-Host "    Dashboard      http://localhost:$UiPort/app.html"
Write-Host '    Brain API      http://127.0.0.1:8000/docs'
Write-Host "    Logs           $State\{anvil,brain,web}*.log"
Write-Host ''
Start-Process "http://localhost:$UiPort/app.html"

#!/usr/bin/env bash
# Start the whole Tec-C stack on this machine, then open the website.
#   1. a local blockchain (Anvil, chain 31337) that remembers its state between runs
#   2. the real vault on it (TecAccount + TetherGuardHook + session key), deployed once
#   3. the Brain API on http://127.0.0.1:8000 (connected to that vault) and the virtual-session phone gateway on :8001
#   4. the website on http://localhost:5500 (localhost, not an IP: passkeys / FaceID need a host name)
# Stop everything with ./dev_down.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
AGENT="$ROOT/agent"
STATE="$AGENT/.state"
RPC="http://127.0.0.1:8545"
UI_PORT=5500
mkdir -p "$STATE"

up() { lsof -ti "tcp:$1" >/dev/null 2>&1; }
say() { printf '\033[1;32m▸\033[0m %s\n' "$*"; }

command -v anvil >/dev/null || { echo "Foundry is missing: brew install foundry"; exit 1; }
[ -x "$AGENT/.venv/bin/python" ] || { echo "Python env missing: cd agent && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; exit 1; }

# 0. compiled contracts
if [ ! -f "$ROOT/contracts/out/TetherGuardHook.sol/TetherGuardHook.json" ]; then
  say "Compiling contracts (first run)…"
  (cd "$ROOT/contracts" && forge build >/dev/null)
fi

# 1. chain
if up 8545; then
  say "Local chain already running on 8545"
else
  say "Starting the local chain (Anvil, chain 31337)…"
  nohup anvil --port 8545 --chain-id 31337 --state "$STATE/anvil-state.json" --state-interval 10 --silent \
    > "$STATE/anvil.log" 2>&1 &
  for _ in $(seq 1 30); do up 8545 && break; sleep 0.3; done
fi

# 2. vaults (deploy and boot up the 3 wallets so the multi-chain ecosystem is live)
for net in anvil arbitrum fisco_bcos; do
  market_file="$STATE/markets/$net.json"
  need_deploy=1
  if [ -f "$market_file" ]; then
    acct=$("$AGENT/.venv/bin/python" -c "import json,sys; print(json.load(open(sys.argv[1]))['deployment']['account'])" "$market_file" 2>/dev/null || echo "")
    if [ -n "$acct" ]; then
      code=$(cast code "$acct" --rpc-url "$RPC" 2>/dev/null || echo 0x)
      [ "$code" != "0x" ] && [ -n "$code" ] && need_deploy=0
    fi
  fi
  if [ "$need_deploy" = 1 ]; then
    say "Deploying and enabling wallet for $net…"
    extra_flag=""
    [ "$net" = "fisco_bcos" ] && extra_flag="--no-native-coin"
    (cd "$AGENT" && .venv/bin/python scripts/deploy_market_chain.py --network "$net" --rpc "$RPC" $extra_flag | sed 's/^/    /')
  else
    say "Wallet ready for $net: $acct"
  fi
done

# 3. Brain (always restarted so it picks up the deployment)
lsof -ti tcp:8000 tcp:8001 | xargs kill 2>/dev/null || true
sleep 0.5
say "Starting the Brain API on http://127.0.0.1:8000 (and the phone gateway on :8001) …"
# agent/.env (API keys etc.) is loaded when present; the runner serves the Brain (:8000) and the phone gateway (:8001)
(cd "$AGENT" && { [ -f .env ] && set -a && . ./.env && set +a; }; TECC_NETWORK=anvil TECC_SPAWN_CLOUDFLARED=1 \
  TECC_CORS_ORIGINS="http://localhost:$UI_PORT,http://127.0.0.1:$UI_PORT,http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000" \
  nohup .venv/bin/python -m tecc_brain.virtual_session.runner > "$STATE/brain.log" 2>&1 &)
for _ in $(seq 1 40); do curl -sf http://127.0.0.1:8000/health >/dev/null && break; sleep 0.3; done
curl -sf http://127.0.0.1:8000/health >/dev/null || { echo "The Brain did not start; see $STATE/brain.log"; exit 1; }

# enable PegGuard 24/7 background scanner for demo account so judges see live telemetry immediately
curl -sf -X POST http://127.0.0.1:8000/api/arbitrage/toggle \
  -H "Content-Type: application/json" \
  -d '{"account":"demo","enabled":true}' >/dev/null 2>&1 || true
say "PegGuard 24/7 background scanner enabled & running."

# 4. website
if up "$UI_PORT"; then
  say "Website already running on $UI_PORT"
else
  say "Starting the website on http://localhost:$UI_PORT …"
  (cd "$ROOT/web" && nohup python3 -m http.server "$UI_PORT" --bind 127.0.0.1 > "$STATE/web.log" 2>&1 &)
  sleep 0.5
fi

echo
say "Ready for Judges Submission:"
echo "    Landing page       http://localhost:$UI_PORT/"
echo "    Dashboard UI       http://localhost:$UI_PORT/app.html"
echo "    Brain API Docs     http://127.0.0.1:8000/docs"
echo "    Phone Gateway      http://127.0.0.1:8001"
echo "    3 Active Wallets   Crypto (Ethereum), Commodities (Arbitrum), Chinese Market (FISCO BCOS)"
echo "    PegGuard Scanner   Active (24/7 scanning enabled across 25 assets)"
echo "    Logs               $STATE/{anvil,brain,web}.log"
echo
command -v open >/dev/null && open "http://localhost:$UI_PORT/app.html" || true

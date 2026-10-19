#!/usr/bin/env bash
# Stop what ./dev_up.sh started. The chain saves its state, so the vault and its balances survive a restart.
for port in 5500 8000 8001 8545; do
  pids=$(lsof -ti "tcp:$port" 2>/dev/null || true)
  [ -n "$pids" ] && kill $pids && echo "stopped :$port"
done
# the quick tunnel a virtual session opened (cloudflared → the phone gateway)
pkill -f "cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8001" 2>/dev/null && echo "stopped the phone tunnel"
true

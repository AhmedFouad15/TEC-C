@echo off
cd /d "%~dp0"
echo Starting Tec-C Cloudflare HTTPS Tunnel...
.venv\Scripts\python.exe start_tunnel.py
pause

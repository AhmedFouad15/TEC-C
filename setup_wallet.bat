@echo off
if exist "agent\.venv\Scripts\python.exe" (
    agent\.venv\Scripts\python.exe setup_wallet_env.py %*
) else (
    python setup_wallet_env.py %*
)

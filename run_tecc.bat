@echo off
if exist "agent\.venv\Scripts\python.exe" (
    agent\.venv\Scripts\python.exe run_tecc.py %*
) else (
    python run_tecc.py %*
)

@echo off
cd /d "%~dp0"

if /I "%~1"=="api" (
    py -m uvicorn api:app --app-dir src --host 127.0.0.1 --port 8000
) else (
    py src\rpc_server.py
)

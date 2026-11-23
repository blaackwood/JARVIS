@echo off
rem Abre o Jarvis Agent UI (servidor local em 127.0.0.1:8765 + janela do Edge).
cd /d "%~dp0.."
set PYTHONUTF8=1
".venv\Scripts\python.exe" "_jarvis_agent_ui\server.py" %*

@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -c "import requests, pyperclip, customtkinter, lupa" >nul 2>nul
if errorlevel 1 (
    echo Preparing the environment - first start, or Python was updated or removed...
    call "%~dp0setup_env.bat"
    if errorlevel 1 (
        echo Could not prepare the environment. Run install.bat to see what went wrong.
        pause
        exit /b 1
    )
)
start "" ".venv\Scripts\pythonw.exe" "poe_assistant.py"

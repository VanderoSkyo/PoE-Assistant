@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -c "import requests, pyperclip, customtkinter, lupa" >nul 2>nul
if errorlevel 1 (
    call "%~dp0setup_env.bat"
    if errorlevel 1 (
        echo Could not prepare the environment.
        pause
        exit /b 1
    )
)
".venv\Scripts\python.exe" "poe_assistant.py"
echo.
echo The application has closed. Details are in poe_assistant.log (see the settings panel for the folder).
pause

@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please run install.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" "poe_assistant.py"
echo.
echo The application has closed. Details are in poe_assistant.log (see the settings panel for the folder).
pause

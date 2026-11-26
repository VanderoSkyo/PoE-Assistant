@echo off
rem Creates or repairs the private Python environment (.venv) next to the app.
rem It does not depend on where Python is installed (C:\Program Files\Python312, %LOCALAPPDATA%\Python\pythoncore-3.14-64, ...):
rem the "py" launcher finds every installed version, and the first one that can install all dependencies is used.
rem Exit code 0 = environment ready, 1 = failed.
setlocal EnableExtensions
cd /d "%~dp0"

rem 1) is there already a working environment? (it breaks when the Python it was built from is uninstalled/upgraded)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import requests, pyperclip, customtkinter, lupa" >nul 2>nul
    if not errorlevel 1 exit /b 0
    echo The existing environment is broken or incomplete - rebuilding it...
    rmdir /s /q ".venv"
)

rem 2) try the installed Python versions one after another (newest ones last: some packages lag behind new releases)
for %%V in (3.13 3.12 3.11 3.14 3.10) do (
    call :try_py %%V
    if not errorlevel 1 exit /b 0
)

rem 3) last resort: whatever "python" is on PATH
call :try_cmd python
if not errorlevel 1 exit /b 0
exit /b 1

:try_py
py -%1 -c "import sys" >nul 2>nul
if errorlevel 1 exit /b 1
echo Trying Python %1 ...
py -%1 -m venv .venv >nul 2>nul
if errorlevel 1 goto :clean_fail
call :install_deps
if errorlevel 1 goto :clean_fail
echo Environment ready (Python %1).
exit /b 0

:try_cmd
%1 -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 exit /b 1
echo Trying "%1" from PATH ...
%1 -m venv .venv >nul 2>nul
if errorlevel 1 goto :clean_fail
call :install_deps
if errorlevel 1 goto :clean_fail
echo Environment ready.
exit /b 0

:install_deps
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>nul
rem lupa must come as a ready-made wheel (no compiler on the user's PC); the other packages are pure Python
".venv\Scripts\python.exe" -m pip install --only-binary lupa -r requirements.txt
exit /b %errorlevel%

:clean_fail
if exist ".venv" rmdir /s /q ".venv"
exit /b 1

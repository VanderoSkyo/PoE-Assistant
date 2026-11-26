@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title PoE Assistant - installer
echo.
echo  === PoE Assistant installer ===
echo.

set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY goto :nopython

%PY% -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto :nopython

echo Using:
%PY% --version
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 goto :fail
)

echo Installing dependencies - this can take a minute...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo Creating desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1"

echo.
echo  Installation finished.
echo  On the first start the app downloads the Path of Building data (internet connection needed).
echo.
choice /m "Start PoE Assistant now"
if errorlevel 2 goto :end
call "%~dp0run.bat"
goto :end

:nopython
echo  Python 3.10 or newer was not found.
echo  Opening the download page. During setup tick "Add python.exe to PATH", then run install.bat again.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1

:fail
echo.
echo  Something went wrong - see the messages above.
pause
exit /b 1

:end
endlocal

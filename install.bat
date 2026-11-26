@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title PoE Assistant - installer
echo.
echo  === PoE Assistant installer ===
echo.
echo Preparing the Python environment - this can take a minute...
call "%~dp0setup_env.bat"
if errorlevel 1 goto :nopython

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
echo.
echo  Could not set up the Python environment.
echo  Make sure Python 3.10 or newer is installed (python.org or the Python Install Manager;
echo  Python 3.12 or 3.13 are the safest choices) and run install.bat again.
echo  Opening the download page...
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1

:end
endlocal

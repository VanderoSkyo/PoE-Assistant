@echo off
rem Builds the standalone version: PoE Assistant.exe with its own Python (no Python needed on the user's PC),
rem a portable zip and - when Inno Setup 6 is installed - Output\PoE-Assistant-Setup-<version>.exe
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call "%~dp0setup_env.bat"
if not exist ".venv\Scripts\python.exe" goto :noenv

".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --onedir --name "PoE Assistant" --collect-all customtkinter --collect-all lupa --hidden-import pob_engine --hidden-import pob_updater poe_assistant.py
if errorlevel 1 goto :fail

echo.
echo Self-test of the built application...
start /wait "" "dist\PoE Assistant\PoE Assistant.exe" --selftest
if errorlevel 1 goto :selftest_failed

for /f %%v in ('.venv\Scripts\python.exe tools\get_version.py') do set "APPVER=%%v"
if not defined APPVER set "APPVER=0.0.0"
if not exist "Output" mkdir "Output"

echo Creating the portable zip...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\PoE Assistant\*' -DestinationPath 'Output\PoE-Assistant-portable-%APPVER%.zip' -Force"

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" goto :compile
set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" goto :compile
echo.
echo Inno Setup 6 was not found - only the portable zip was created (Output folder).
echo Install it from https://jrsoftware.org/isinfo.php and run this script again to get a Setup.exe.
goto :end

:compile
"%ISCC%" /DMyAppVersion=%APPVER% installer.iss
if errorlevel 1 goto :fail
echo.
echo Done. See the Output folder.
goto :end

:selftest_failed
echo.
echo The built application failed its self-test. Details: %LOCALAPPDATA%\PoE Assistant\selftest.txt
goto :fail

:noenv
echo Could not prepare the Python environment. Run install.bat first.
goto :fail

:fail
echo.
echo Build failed - see the messages above.
pause
exit /b 1

:end
endlocal

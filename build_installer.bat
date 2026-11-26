@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto :noenv

".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --onedir --name "PoE Assistant" --collect-all customtkinter --collect-all lupa --hidden-import pob_engine --hidden-import pob_updater poe_assistant.py
if errorlevel 1 goto :fail

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" goto :compile
set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" goto :compile
echo.
echo Inno Setup 6 was not found. The portable build is in dist\PoE Assistant\ - zip that folder to share it.
goto :end

:compile
"%ISCC%" installer.iss
goto :end

:noenv
echo Run install.bat first.
goto :fail

:fail
echo.
echo Build failed - see the messages above.
pause
exit /b 1

:end
endlocal

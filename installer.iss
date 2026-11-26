; Inno Setup script - compile with build_installer.bat after PyInstaller finished.
[Setup]
AppName=PoE Assistant
AppVersion=0.1.0
AppPublisher=PoE Assistant authors
DefaultDirName={localappdata}\Programs\PoE Assistant
DefaultGroupName=PoE Assistant
OutputDir=Output
OutputBaseFilename=PoE-Assistant-Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
UninstallDisplayName=PoE Assistant
LicenseFile=LICENSE

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\PoE Assistant\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\PoE Assistant"; Filename: "{app}\PoE Assistant.exe"
Name: "{autodesktop}\PoE Assistant"; Filename: "{app}\PoE Assistant.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PoE Assistant.exe"; Description: "Start PoE Assistant"; Flags: nowait postinstall skipifsilent

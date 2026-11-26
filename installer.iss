; Inno Setup script - compiled by build_installer.bat (or by the GitHub Actions workflow) after PyInstaller finished.
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif

[Setup]
AppId={{0C6B6EBC-6571-452D-A667-D6A099B1199C}
AppName=PoE Assistant
AppVersion={#MyAppVersion}
AppPublisher=VanderSky
DefaultDirName={localappdata}\Programs\PoE Assistant
DefaultGroupName=PoE Assistant
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=PoE-Assistant-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayName=PoE Assistant
LicenseFile=LICENSE
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\PoE Assistant\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\PoE Assistant"; Filename: "{app}\PoE Assistant.exe"
Name: "{autodesktop}\PoE Assistant"; Filename: "{app}\PoE Assistant.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PoE Assistant.exe"; Description: "Start PoE Assistant"; Flags: nowait postinstall skipifsilent

[Code]
// On uninstall, offer to remove the settings, log and the downloaded Path of Building data as well.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\PoE Assistant');
    if DirExists(DataDir) then
      if MsgBox('Also delete your settings and the downloaded Path of Building data?', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;

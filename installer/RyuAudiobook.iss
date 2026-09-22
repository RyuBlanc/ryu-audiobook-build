# Inno Setup script for the core Ryu's Audiobook desktop application.
# User books, voices, models, and settings live under %USERPROFILE% and are
# intentionally NOT removed by this installer or its uninstaller.

#define MyAppName "Ryu's Audiobook"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "RyuBlanc"
#define MyAppExeName "Ryu's Audiobook.exe"

[Setup]
AppId={{8B8C8B8C-2F0A-4D6C-9B52-8B4A2C7F9A01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Ryu's Audiobook
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer-output
OutputBaseFilename=Ryu's Audiobook Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
UninstallDisplayName={#MyAppName}

[Files]
Source: "dist\Ryu's Audiobook\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Deliberately do not remove {userappdata}, Documents, or the user's
; Ryu's Audiobook data. Application data is outside {app}.

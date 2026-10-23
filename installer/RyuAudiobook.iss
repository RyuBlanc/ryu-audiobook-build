; Inno Setup script for the core Ryu's Audiobook desktop application.
; User books, voices, models, and settings live under %USERPROFILE% and are
; intentionally NOT removed by this installer or its uninstaller.

#define MyAppName "Ryu's Audiobook"
#include "version.generated.iss"
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
OutputBaseFilename=Ryu's Audiobook Setup Payload
Compression=lzma
SolidCompression=yes
WizardStyle=modern dark hidebevels includetitlebar
WizardResizable=yes
WizardSizePercent=125,110
WizardBackColor=#05060A
WizardImageFile=..\assets\installer_brand_panel.png
WizardImageBackColor=#05060A
WizardSmallImageFile=..\assets\ryu_audiobook_logo.png
WizardSmallImageBackColor=#05060A
DefaultDialogFontName=Segoe UI
SetupIconFile=..\assets\ryu_audiobook_logo.ico
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
CloseApplications=yes
CloseApplicationsFilter=Ryu's Audiobook.exe
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#MyAppVersion}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName}
VersionInfoProductName={#MyAppName}

[Files]
Source: "..\dist\Ryu's Audiobook\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "startmenuicon"; Description: "Create a Start menu shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

; The outer HTML bootstrapper launches the installed application from its completion page.

[UninstallDelete]
; Deliberately do not remove user data outside {app}.

[Messages]
WelcomeLabel1=Welcome to [name/ver]
WelcomeLabel2=Install Ryu's Audiobook Dragon Studio on this computer.\n\nYour books, voice profiles, models, and settings are kept in your user profile and are not removed by uninstalling the application.
FinishedHeadingLabel=Ryu's Audiobook is ready
FinishedLabel=Setup has finished installing Ryu's Audiobook. Launch Dragon Studio to continue your audiobook projects.

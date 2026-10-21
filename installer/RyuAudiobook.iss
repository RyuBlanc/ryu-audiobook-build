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
OutputBaseFilename=Ryu's Audiobook Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
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
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Deliberately do not remove user data outside {app}.

[Messages]
WelcomeLabel1=Welcome to [name/ver]
WelcomeLabel2=Install Ryu's Audiobook Dragon Studio on this computer.\n\nYour books, voice profiles, models, and settings are kept in your user profile and are not removed by uninstalling the application.
FinishedHeadingLabel=Ryu's Audiobook is ready
FinishedLabel=Setup has finished installing Ryu's Audiobook. Launch Dragon Studio to continue your audiobook projects.

[Code]
procedure InitializeWizard();
var
  I: Integer;
begin
  { Premium V2-inspired dark canvas and warm crimson/gold identity.
    Set every wizard label explicitly so default black text cannot disappear
    against the dark page surfaces. Keep native controls and keyboard support. }
  WizardForm.Color := $000F0A09;
  WizardForm.MainPanel.Color := $001A130F;
  WizardForm.InnerPage.Color := $001A130F;
  WizardForm.Font.Name := 'Segoe UI';

  for I := 0 to WizardForm.ComponentCount - 1 do
  begin
    if WizardForm.Components[I] is TLabel then
    begin
      TLabel(WizardForm.Components[I]).Font.Name := 'Segoe UI';
      TLabel(WizardForm.Components[I]).Font.Color := $00B8ACA5;
    end;
  end;

  { Restore higher-contrast gold for page and completion headings. }
  WizardForm.PageNameLabel.Font.Color := $006AB0D6;
  WizardForm.WelcomeLabel1.Font.Color := $006AB0D6;
  WizardForm.FinishedHeadingLabel.Font.Color := $006AB0D6;
  WizardForm.PageDescriptionLabel.Font.Color := $00E0D7D0;
  WizardForm.WelcomeLabel2.Font.Color := $00E0D7D0;
  WizardForm.FinishedLabel.Font.Color := $00E0D7D0;
end;

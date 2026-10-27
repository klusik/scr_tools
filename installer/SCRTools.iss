; Project: SCR Tools
; Repository: SCR-Tools (local Git-ready source)
; File path: installer/SCRTools.iss
; Module Type: Per-user Windows installer
; Purpose: Install the standalone application without elevation.
; Responsibilities: Create shortcuts, enforce shutdown and clean auto-start.
; Author: Rudolf Klusal
; License: MIT

#ifndef AppVersion
  #error AppVersion must be supplied by deploy.ps1.
#endif
#ifndef SourceExe
  #error SourceExe must point to the PyInstaller SCRTools.exe.
#endif
#ifndef OutputDir
  #error OutputDir must be supplied by deploy.ps1.
#endif
#ifndef ProjectRoot
  #error ProjectRoot must be supplied by deploy.ps1.
#endif

[Setup]
AppId={{7430958D-2E56-41C0-B7FC-8F90A7906D15}
AppName=SCR Tools
AppVersion={#AppVersion}
AppVerName=SCR Tools {#AppVersion}
AppPublisher=Rudolf Klusal
AppCopyright=Copyright (c) 2026 Rudolf Klusal
DefaultDirName={localappdata}\Programs\SCR Tools
DefaultGroupName=SCR Tools
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
; x64 is accepted by Inno 6 and 7; newer compilers name this x64os.
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0.22000
WizardStyle=modern
LicenseFile={#ProjectRoot}\LICENSE
SetupIconFile={#ProjectRoot}\assets\icons\scr_tools.ico
UninstallDisplayIcon={app}\SCRTools.exe
VersionInfoVersion={#AppVersion}.0
OutputDir={#OutputDir}
OutputBaseFilename=SCRTools_{#AppVersion}_Setup
Compression=lzma2
SolidCompression=yes
AppMutex=Local\SCRTools.RudolfKlusal.Singleton
SetupMutex=Local\SCRTools.RudolfKlusal.Setup
; The app's close/X handler hides it, so use its tray Exit before setup.
; Do not ask Restart Manager to forcibly close or restart the application.
CloseApplications=no
RestartApplications=no
Uninstallable=yes
UninstallLogMode=append

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.LaunchSCRTools=Launch SCR Tools
english.StartupRemovalFailed=Windows could not remove the SCR Tools auto-start entry. Remove SCR Tools from Windows Startup apps if it remains listed.

[Files]
Source: "{#SourceExe}"; DestDir: "{app}"; DestName: "SCRTools.exe"; Flags: ignoreversion
Source: "{#ProjectRoot}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\SCR Tools"; Filename: "{app}\SCRTools.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\SCRTools.exe"; Description: "{cm:LaunchSCRTools}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
{ Remove only this application's per-user auto-start value.
  Args: CurUninstallStep is the current Inno uninstall lifecycle step.
  Returns: No value; settings, logs and screenshots are preserved.
  Failure: Report a denied registry operation without deleting other values. }
begin
  if CurUninstallStep = usUninstall then
  begin
    if RegValueExists(HKCU,
      'Software\Microsoft\Windows\CurrentVersion\Run', 'SCR Tools') then
    begin
      if not RegDeleteValue(HKCU,
        'Software\Microsoft\Windows\CurrentVersion\Run', 'SCR Tools') then
      begin
        Log('Could not remove the SCR Tools auto-start registry value.');
        SuppressibleMsgBox(
          CustomMessage('StartupRemovalFailed'),
          mbInformation, MB_OK, IDOK);
      end;
    end;
  end;
end;

; Inno Setup script: makes DLIS_Teacher_Assistant_Setup.exe (install for the current user, no admin needed).
; Build it with build_windows.bat (after Inno Setup is installed) or with the GitHub workflow.
#define AppName "DLIS Teacher Assistant"
#define AppVersion "1.0.0"
#define AppExe "DLIS_Teacher_Assistant.exe"

[Setup]
AppId={{B7D1F3A2-5C0E-4E5B-9A55-2F6D0C1E7A10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Dar Luqman Al-Hakim International School
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=DLIS_Teacher_Assistant_Setup
SetupIconFile=..\resources\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a shortcut on the desktop"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\DLIS_Teacher_Assistant\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Open {#AppName} now"; Flags: nowait postinstall

[Code]
// The app window needs Microsoft Edge WebView2 (already on recent Windows 10 and 11).
function WebView2Installed: Boolean;
var v: String;
begin
  Result := RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v)
         or RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v)
         or RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v);
  if Result then Result := (v <> '') and (v <> '0.0.0.0');
end;

function InitializeSetup: Boolean;
var code: Integer;
begin
  Result := True;
  if not WebView2Installed then
    if MsgBox('This program needs "Microsoft Edge WebView2", which was not found on this computer.' + #13#10 + #13#10 +
              'Press Yes to open the Microsoft download page (install it, then run this setup again), or No to continue anyway.',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      ShellExec('open', 'https://developer.microsoft.com/microsoft-edge/webview2/', '', '', SW_SHOWNORMAL, ewNoWait, code);
      Result := False;
    end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var code: Integer;
begin
  // an older copy may be running near the clock: close it before files are replaced
  if CurStep = ssInstall then
    Exec('taskkill.exe', '/F /IM {#AppExe}', '', SW_HIDE, ewWaitUntilTerminated, code);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var code: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    Exec('taskkill.exe', '/F /IM {#AppExe}', '', SW_HIDE, ewWaitUntilTerminated, code);
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'DLIS Teacher Assistant');
  end;
end;

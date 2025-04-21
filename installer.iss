#define MyAppName "Hotel Beacons"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Hotel Beacons"
#define MyAppExeName "HotelBeacons.exe"
#define MyStartupExeName "HotelBeaconsStartup.exe"

[Setup]
AppId={{8F4E9A1D-7B3C-4E5F-9A2B-1C3D4E5F6A7B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=installer
OutputBaseFilename=HotelBeacons_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Start {#MyAppName} when Windows starts"; GroupDescription: "Additional tasks:"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\{#MyStartupExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#MyStartupExeName}"; Tasks: startupicon; Flags: runhidden

[UninstallRun]
Filename: "{app}\{#MyStartupExeName}"; Parameters: "--remove"; Flags: runhidden; RunOnceId: "RemoveStartup"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end; 
#ifndef MyAppVersion
#define MyAppVersion "1.0.0"
#endif
#define MyAppName "ASC SKU"
#define MyAppPublisher "ShuGe"

[Setup]
AppId={{8E6B2C1A-4D7F-4A19-9C3E-000000SKU001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\ASC SKU
DefaultGroupName={#MyAppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
UsePreviousAppDir=no
CloseApplications=force
OutputDir=..\dist
OutputBaseFilename=ASC-SKU-Setup-{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\ASC SKU.exe
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\ASC SKU\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs overwritereadonly uninsremovereadonly

[Icons]
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\ASC SKU.exe"
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\ASC SKU.exe"

[Run]
Filename: "{app}\ASC SKU.exe"; Description: "Launch ASC SKU"; Flags: nowait postinstall skipifsilent

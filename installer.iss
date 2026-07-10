; installer.iss — gera o instalador (Setup.exe) do Dota Level Up Auto Lobby.
; Requer Inno Setup 6+ (ISCC.exe). Rodar depois de `python build.py`.
;
; Compilar:
;   "C:\Program Files\Inno Setup 7\ISCC.exe" installer.iss

#define MyAppName "Dota Level Up Auto Lobby"
#ifndef MyAppVersion
  #define MyAppVersion "2.2.2"
#endif
#define MyAppPublisher "Bastos"
#define MyAppExeName "start.exe"
#define MyDistDir "dist\Dota-level-up-lobby"

[Setup]
AppId={{9F4E6A2C-2C1B-4C7E-9B0D-7E1D9C6B9A11}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName=C:\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename=Dota-Level-Up-Lobby-Setup-{#MyAppVersion}
SetupIconFile=level-up.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#MyDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\level-up.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\level-up.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

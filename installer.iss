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
Name: "defenderexclusion"; Description: "Adicionar a pasta de instalação às exclusões do Windows Defender (recomendado - evita bloqueio/falso positivo de trojan nos .exe)"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#MyDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\level-up.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\level-up.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Cmd: String;
begin
  // Add-MpPreference precisa de admin - o instalador roda com
  // PrivilegesRequired=lowest, então eleva só esse comando via ShellExec
  // 'runas' (dispara UAC isolado, sem exigir o instalador inteiro elevado).
  // Se o usuário negar o UAC, só falha essa etapa - instalação segue normal.
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('defenderexclusion') then
  begin
    Cmd := '-NoProfile -WindowStyle Hidden -Command "Add-MpPreference -ExclusionPath ''' + ExpandConstant('{app}') + '''"';
    ShellExec('runas', 'powershell.exe', Cmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

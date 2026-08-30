#define MyAppName "PRIME TRADER"
#define MyAppVersion "1.3.1"
#define MyAppPublisher "PRIME"
#define MyAppExeName "PrimeAITrader.exe"

[Setup]
AppId={{D648BC0B-532F-4A0B-A234-4B85C89FE5B4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
; Mantém a pasta histórica para atualização in-place das versões anteriores.
DefaultDirName={autopf}\PrimeAITrader
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=license_pt_BR.txt
OutputDir=..\release
OutputBaseFilename=PrimeTrader-Setup-x64
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Instalador do PRIME TRADER
VersionInfoProductName={#MyAppName}
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na Área de Trabalho"; GroupDescription: "Atalhos adicionais:"; Flags: unchecked
Name: "cleancache"; Description: "Limpar cache e modelos de versões antigas (mantém chaves, configurações e histórico)"; GroupDescription: "Atualização segura:"; Flags: checkedonce

[Files]
Source: "..\release\PrimeAITrader.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\RELEASE_NOTES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config\apis.example.json"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "..\scripts\Limpar-Cache-PrimeAITrader.cmd"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
Type: filesandordirs; Name: "{app}\cache"
Type: filesandordirs; Name: "{app}\models"
Type: filesandordirs; Name: "{app}\temp"
Type: filesandordirs; Name: "{app}\old_versions"
Type: filesandordirs; Name: "{app}\updates"
Type: filesandordirs; Name: "{app}\__pycache__"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{group}\Limpar cache e modelos antigos"; Filename: "{app}\Limpar-Cache-PrimeAITrader.cmd"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir PRIME TRADER"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssInstall) and WizardIsTaskSelected('cleancache') then
  begin
    DelTree(ExpandConstant('{userappdata}\PrimeAITrader\models'), True, True, True);
    DelTree(ExpandConstant('{userappdata}\PrimeAITrader\cache'), True, True, True);
    DelTree(ExpandConstant('{userappdata}\PrimeAITrader\temp'), True, True, True);
    DelTree(ExpandConstant('{userappdata}\PrimeAITrader\old_versions'), True, True, True);
    DelTree(ExpandConstant('{userappdata}\PrimeAITrader\updates'), True, True, True);
    DelTree(ExpandConstant('{localappdata}\PrimeAITrader\models'), True, True, True);
    DelTree(ExpandConstant('{localappdata}\PrimeAITrader\cache'), True, True, True);
    DelTree(ExpandConstant('{localappdata}\PrimeAITrader\temp'), True, True, True);
  end;
end;

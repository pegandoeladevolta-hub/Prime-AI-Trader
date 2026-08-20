#define MyAppName "PRIME AI TRADER"
#define MyAppVersion "0.2.0"
#define MyAppPublisher "PRIME"
#define MyAppExeName "PrimeAITrader.exe"

[Setup]
AppId={{D648BC0B-532F-4A0B-A234-4B85C89FE5B4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\PrimeAITrader
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=license_pt_BR.txt
OutputDir=..\release
OutputBaseFilename=PrimeAITrader-Setup-x64
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
VersionInfoDescription=Instalador do PRIME AI TRADER
VersionInfoProductName={#MyAppName}
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na Área de Trabalho"; GroupDescription: "Atalhos adicionais:"; Flags: unchecked

[Files]
Source: "..\release\PrimeAITrader.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\RELEASE_NOTES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config\apis.example.json"; DestDir: "{app}\config"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir PRIME AI TRADER"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

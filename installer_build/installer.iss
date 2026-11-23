#define MyAppName "JARVIS"
#define MyAppVersion "0.2.0"
#define MyAppPublisher "blaackwood"
#define MyAppExeName "JARVIS.exe"

[Setup]
AppId={{B2D6F9A1-70C8-4E3A-9F51-2C6A10D18A44}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\JARVIS
DefaultGroupName=JARVIS
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=release
OutputBaseFilename=JARVIS-Setup
SetupIconFile=..\config\jarvis.ico
UninstallDisplayIcon={app}\JARVIS.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Dirs]
Name: "{app}\config"
Name: "{app}\memory"
Name: "{app}\memory\tasks"
Name: "{app}\reports"

[Files]
Source: "package\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; User credentials, config/api_keys.json, memory, histories and task state are never bundled.

[Icons]
Name: "{autoprograms}\JARVIS"; Filename: "{app}\JARVIS.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\JARVIS"; Filename: "{app}\JARVIS.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\JARVIS.exe"; Description: "Iniciar JARVIS"; Flags: postinstall nowait skipifsilent

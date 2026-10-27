#ifndef AppVersion
  #define AppVersion "0.5.0"
#endif
#ifndef PayloadDir
  #error PayloadDir deve apontar para o pacote validado
#endif
#ifndef OutputDir
  #error OutputDir deve apontar para a pasta de artefatos
#endif

[Setup]
AppId={{EBF82E2A-C389-4FFD-9540-F9568B87DDA0}
AppName=Sumi
AppVersion={#AppVersion}
VersionInfoVersion={#AppVersion}
VersionInfoTextVersion={#AppVersion}
VersionInfoProductVersion={#AppVersion}
AppPublisher=Lyon Müller
AppPublisherURL=https://github.com/LyonMuller/sumi
AppSupportURL=https://github.com/LyonMuller/sumi/issues
AppUpdatesURL=https://github.com/LyonMuller/sumi/releases
DefaultDirName={localappdata}\Programs\Sumi
DefaultGroupName=Sumi
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.19041
OutputDir={#OutputDir}
OutputBaseFilename=Sumi-Setup-{#AppVersion}
SetupIconFile=..\assets\brand\app-icon.ico
UninstallDisplayIcon={app}\Sumi.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
DisableWelcomePage=no
CloseApplications=yes
RestartApplications=no
InfoBeforeFile=TESTE_LOCAL.txt
UninstallDisplayName=Sumi

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; Flags: unchecked

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Sumi"; Filename: "{app}\Sumi.exe"; AppUserModelID: "Sumi.Desktop"
Name: "{group}\Guia rápido"; Filename: "{app}\_internal\GUIA_RAPIDO.html"
Name: "{autodesktop}\Sumi"; Filename: "{app}\Sumi.exe"; Tasks: desktopicon; AppUserModelID: "Sumi.Desktop"

; No driver registration, browser extension installation, auto-run or downloads.
; Per-user settings remain after uninstall; never delete them recursively.

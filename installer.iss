; Killcam installer (Inno Setup 6). Per-user install, no admin rights needed.
; /DChannel=demo builds "Killcam Demo": its own AppId, folder and shortcuts, so it installs
; next to the normal Killcam without touching it.
#define AppVersion "2.0.2"
#ifndef AppDir
  #define AppDir "dist\Killcam"
#endif
#ifndef Channel
  #define Channel "main"
#endif
#if Channel == "demo"
  #define AppName "Killcam Demo"
  #define ExeName "KillcamDemo.exe"
  #define AppGuid "{{5D2E7A91-3C48-4F6B-A0D2-7E19C4B8F512}"
  #define SetupName "KillcamDemoSetup"
  #define InstallDir "KillcamDemo"
#else
  #define AppName "Killcam"
  #define ExeName "Killcam.exe"
  #define AppGuid "{{8C1F4B2E-6A4D-4E0B-9C51-4B7A2D1E9F30}"
  #define SetupName "KillcamSetup"
  #define InstallDir "Killcam"
#endif

[Setup]
AppId={#AppGuid}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Killcam
AppPublisherURL=https://github.com/killcam-app/killcam
DefaultDirName={localappdata}\Programs\{#InstallDir}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename={#SetupName}
SetupIconFile={#SourcePath}assets\killcam.ico
UninstallDisplayIcon={app}\{#ExeName}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/ultra64
SolidCompression=yes
CloseApplications=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#AppDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#ExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#ExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#ExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; self-update runs the installer silently: start the new version afterwards
Filename: "{app}\{#ExeName}"; Flags: nowait; Check: WizardSilent

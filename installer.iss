; Killcam installer (Inno Setup 6). Per-user install, no admin rights needed.
#define AppVersion "2.0.0"
#ifndef AppDir
  #define AppDir "dist\Killcam"
#endif

[Setup]
AppId={{8C1F4B2E-6A4D-4E0B-9C51-4B7A2D1E9F30}
AppName=Killcam
AppVersion={#AppVersion}
AppVerName=Killcam {#AppVersion}
AppPublisher=Killcam
AppPublisherURL=https://github.com/evgenstepanov998-afk/killcam
DefaultDirName={localappdata}\Programs\Killcam
DefaultGroupName=Killcam
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=KillcamSetup
SetupIconFile={#SourcePath}assets\killcam.ico
UninstallDisplayIcon={app}\Killcam.exe
UninstallDisplayName=Killcam
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
Name: "{group}\Killcam"; Filename: "{app}\Killcam.exe"
Name: "{group}\{cm:UninstallProgram,Killcam}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Killcam"; Filename: "{app}\Killcam.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Killcam.exe"; Description: "{cm:LaunchProgram,Killcam}"; Flags: nowait postinstall skipifsilent
; self-update runs the installer silently: start the new version afterwards
Filename: "{app}\Killcam.exe"; Flags: nowait; Check: WizardSilent

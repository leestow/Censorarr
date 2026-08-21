#define MyAppName "Censorarr"
#define MyAppPublisher "Censorarr"
#define MyAppURL "https://github.com/leestow/Censorarr"
#define MyAppExeName "Censorarr.exe"
#define MyAppVersion GetEnv("CENSORARR_APP_VERSION")
#define MyFileVersion GetEnv("CENSORARR_FILE_VERSION")
#if MyAppVersion == ""
  #define MyAppVersion "1.6.9"
#endif
#if MyFileVersion == ""
  #define MyFileVersion "1.6.9.0"
#endif

[Setup]
AppId={{5B0FCF70-A2DE-42AF-95CB-9F227E6B083B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\Censorarr
DefaultGroupName=Censorarr
DisableProgramGroupPage=yes
OutputDir=dist-installer
OutputBaseFilename=Censorarr-Setup-{#MyAppVersion}
SetupIconFile=build\censorarr.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
CloseApplicationsFilter=Censorarr.exe
RestartApplications=no
MinVersion=10.0.22000
VersionInfoVersion={#MyFileVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Censorarr Windows Installer
VersionInfoProductName=Censorarr
VersionInfoProductVersion={#MyAppVersion}

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked
Name: "autostart"; Description: "Start Censorarr automatically when I sign in"; GroupDescription: "Startup:"; Flags: checkedonce

[Dirs]
Name: "{commonappdata}\Censorarr"; Permissions: users-modify
Name: "{commonappdata}\Censorarr\config"; Permissions: users-modify
Name: "{commonappdata}\Censorarr\work"; Permissions: users-modify
Name: "{commonappdata}\Censorarr\config\models"; Permissions: users-modify
Name: "{commonappdata}\Censorarr\logs"; Permissions: users-modify

[Files]
Source: "dist\Censorarr\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "build\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\Open Censorarr"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--open-browser"; WorkingDir: "{app}"
Name: "{group}\Censorarr on GitHub"; Filename: "https://github.com/leestow/Censorarr"
Name: "{autodesktop}\Censorarr"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--open-browser"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userstartup}\Censorarr"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--background"; WorkingDir: "{app}"; Tasks: autostart

[Run]
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Installing Microsoft Visual C++ Runtime..."; Flags: waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Parameters: "--open-browser"; Description: "Open Censorarr"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM Censorarr.exe /F >nul 2>&1"; Flags: runhidden; RunOnceId: "StopCensorarr"

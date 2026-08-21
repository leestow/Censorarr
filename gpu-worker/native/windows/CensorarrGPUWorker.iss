#define MyAppName "Censorarr GPU Worker"
#define MyAppPublisher "Censorarr"
#define MyAppURL "https://github.com/leestow/Censorarr"
#define MyAppExeName "CensorarrGPUWorker.exe"
#define MyAppVersion GetEnv("CENSORARR_APP_VERSION")
#define MyFileVersion GetEnv("CENSORARR_FILE_VERSION")
#if MyAppVersion == ""
  #define MyAppVersion "1.6.9"
#endif
#if MyFileVersion == ""
  #define MyFileVersion "1.6.9.0"
#endif

[Setup]
AppId={{92A9E643-4966-4B6F-86BB-719A1A61CA67}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\Censorarr GPU Worker
DefaultGroupName=Censorarr GPU Worker
DisableProgramGroupPage=yes
OutputDir=dist-installer
OutputBaseFilename=Censorarr-GPU-Worker-Setup-{#MyAppVersion}
SetupIconFile=build\censorarr-gpu-worker.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000
VersionInfoVersion={#MyFileVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Censorarr GPU Worker Windows Installer
VersionInfoProductName=Censorarr GPU Worker
VersionInfoProductVersion={#MyAppVersion}

[Tasks]
Name: "downloadruntime"; Description: "Download pinned NVIDIA CUDA 12 / cuBLAS / cuDNN runtime libraries from NVIDIA's PyPI packages (about 1-2 GB; NVIDIA license terms apply)"; Flags: checkedonce

[Dirs]
Name: "{commonappdata}\CensorarrGPUWorker"; Permissions: users-readexec
Name: "{commonappdata}\CensorarrGPUWorker\models"; Permissions: users-readexec
Name: "{commonappdata}\CensorarrGPUWorker\runtime"; Permissions: users-readexec

[Files]
Source: "dist\CensorarrGPUWorker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "build\runtime-manifest.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "build\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\GPU Worker Configuration"; Filename: "{sys}\notepad.exe"; Parameters: """{commonappdata}\CensorarrGPUWorker\worker.env"""
Name: "{group}\Censorarr GPU Worker on GitHub"; Filename: "https://github.com/leestow/Censorarr"
Name: "{group}\NVIDIA Driver Download"; Filename: "https://www.nvidia.com/Download/index.aspx"

[Run]
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Installing Microsoft Visual C++ Runtime..."; Flags: waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Parameters: "--ensure-config"; StatusMsg: "Creating GPU Worker configuration..."; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Parameters: "--install-runtime"; StatusMsg: "Downloading and verifying NVIDIA CUDA 12 / cuBLAS / cuDNN runtime libraries (about 1-2 GB)..."; Flags: runhidden waituntilterminated; Tasks: downloadruntime
Filename: "{app}\{#MyAppExeName}"; Parameters: "--install-service"; StatusMsg: "Installing GPU Worker startup task..."; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Parameters: "--start-service"; StatusMsg: "Starting Censorarr GPU Worker..."; Flags: runhidden waituntilterminated
Filename: "{sys}\notepad.exe"; Parameters: """{commonappdata}\CensorarrGPUWorker\worker.env"""; Description: "Open GPU Worker configuration and token"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--remove-service"; Flags: runhidden; RunOnceId: "RemoveGPUWorkerTask"
Filename: "{cmd}"; Parameters: "/C taskkill /IM CensorarrGPUWorker.exe /F >nul 2>&1"; Flags: runhidden; RunOnceId: "StopGPUWorker"

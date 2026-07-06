; Inno Setup script for WinUC.
; Build the app first (packaging/build.ps1), then compile this with ISCC.exe.

#define AppName "WinUC"
#define AppVersion "2.0.0"
#define AppPublisher "fuba"
#define AppURL "https://github.com/fuba/winuc"
#define AppExeName "WinUC.exe"

[Setup]
AppId={{9E6C1B2A-4E1D-49C7-9B0E-WINUC0000002}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppSupportURL={#AppURL}
DefaultDirName={autopf}\WinUC
DefaultGroupName=WinUC
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=WinUC-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; Driver switching needs admin; install per-machine.
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#AppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startupicon"; Description: "Start WinUC automatically at sign-in"; GroupDescription: "Startup:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
; The PyInstaller COLLECT output directory (dist\WinUC\*).
Source: "..\dist\WinUC\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\WinUC"; Filename: "{app}\{#AppExeName}"; Parameters: "--tray"
Name: "{group}\WinUC Setup"; Filename: "{app}\{#AppExeName}"; Parameters: "--setup"
Name: "{group}\Uninstall WinUC"; Filename: "{uninstallexe}"
Name: "{autodesktop}\WinUC"; Filename: "{app}\{#AppExeName}"; Parameters: "--tray"; Tasks: desktopicon

[Registry]
; Per-user autostart into the tray (only if the task was selected).
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "WinUC"; ValueData: """{app}\{#AppExeName}"" --tray"; \
    Flags: uninsdeletevalue; Tasks: startupicon

[Run]
; Offer to open the setup wizard right after install.
Filename: "{app}\{#AppExeName}"; Parameters: "--setup"; \
    Description: "Run the WinUC setup wizard now"; Flags: postinstall nowait skipifsilent

[UninstallRun]
; Best-effort: restore the dongle's normal Bluetooth driver on uninstall.
Filename: "{app}\{#AppExeName}"; Parameters: "--driver-restore --vid 0x0411 --pid 0x0374"; \
    Flags: runhidden; RunOnceId: "RestoreDongle"

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\WinUC"

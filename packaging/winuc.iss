; Inno Setup script for WinUC.
; Build the app first (packaging/build.ps1), then compile this with ISCC.exe.

#define AppName "Glideleaf"
#define AppVersion "0.1.0"
#define AppPublisher "Glideleaf contributors"
#define AppExeName "Glideleaf.exe"

[Setup]
AppId={{BB0B382A-F9CD-4D93-B431-A5D10768F1D6}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Glideleaf
DefaultGroupName=Glideleaf
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=Glideleaf-Setup-{#AppVersion}
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; Per-user install: no admin needed to install (autostart is per-user HKCU,
; and driver switching self-elevates at runtime with a single UAC prompt).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#AppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startupicon"; Description: "Start Glideleaf automatically at sign-in"; GroupDescription: "Startup:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
; The PyInstaller COLLECT output directory (dist\Glideleaf\*).
Source: "..\dist\Glideleaf\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Glideleaf"; Filename: "{app}\{#AppExeName}"; Parameters: "--tray"
Name: "{group}\Glideleaf Setup"; Filename: "{app}\{#AppExeName}"; Parameters: "--setup"
Name: "{group}\Uninstall Glideleaf"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Glideleaf"; Filename: "{app}\{#AppExeName}"; Parameters: "--tray"; Tasks: desktopicon

[Registry]
; Per-user autostart into the tray (only if the task was selected).
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "WinUC"; ValueData: """{app}\{#AppExeName}"" --tray"; \
    Flags: uninsdeletevalue; Tasks: startupicon

[Run]
; Offer to open the setup wizard right after install.
Filename: "{app}\{#AppExeName}"; Parameters: "--setup"; \
    Description: "Run the Glideleaf setup wizard now"; Flags: postinstall nowait skipifsilent

; Restore a dongle explicitly in Adapter setup before uninstalling.
; Keep shared legacy settings and pairing keys during uninstall.

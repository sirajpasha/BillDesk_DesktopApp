; Inno Setup script for BillDesk Native Mandi POS & ERP
; Usage: ISCC.exe installer\BillDesk.iss
; Or compile via Inno Setup IDE

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#ifndef DistDir
  #define DistDir "..\dist"
#endif

[Setup]
AppId={{9B7E3E52-8D4E-4B0A-9C57-2E8B7A1D4F91}
AppName=BillDesk Desktop
AppVersion={#AppVersion}
AppPublisher=BillDesk
DefaultDirName={autopf}\BillDesk
DefaultGroupName=BillDesk
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#DistDir}
OutputBaseFilename=BillDesk-Desktop-Setup
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayName=BillDesk Desktop
UninstallDisplayIcon={app}\BillDesk.exe
AppMutex=BillDeskDesktopNativeMutex
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#AppVersion}

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Start BillDesk on Windows sign-in"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#DistDir}\BillDesk\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\start.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\start.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\BillDesk"; Filename: "{app}\BillDesk.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\BillDesk"; Filename: "{app}\BillDesk.exe"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userstartup}\BillDesk"; Filename: "{app}\BillDesk.exe"; WorkingDir: "{app}"; Tasks: startup

[Run]
Filename: "{app}\BillDesk.exe"; Description: "Launch BillDesk Native POS"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

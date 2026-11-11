#ifndef AgentVersion
  #error AgentVersion is required
#endif
[Setup]
AppId={{836DEEF0-69F4-4A5A-BD79-C64A2461D9C1}
AppName=Haitoo Hub 连接器
AppVersion={#AgentVersion}
DefaultDirName={localappdata}\Programs\HaitooHubAgent
DefaultGroupName=Haitoo Hub 连接器
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=HaitooHubAgent-windows-x64-{#AgentVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\HaitooHubAgent\HaitooHubAgent.exe
[Tasks]
Name: desktopicon; Description: "创建桌面快捷方式"
[Files]
Source: "..\..\dist\HaitooHubAgent\*"; DestDir: "{app}\HaitooHubAgent"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\dist\HaitooHubAgentConsole\*"; DestDir: "{app}\HaitooHubAgentConsole"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\Haitoo Hub 连接器"; Filename: "{app}\HaitooHubAgent\HaitooHubAgent.exe"; Parameters: "tray"
Name: "{autodesktop}\Haitoo Hub 连接器"; Filename: "{app}\HaitooHubAgent\HaitooHubAgent.exe"; Parameters: "tray"; Tasks: desktopicon
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "HaitooHubAgent"; Flags: uninsdeletevalue
[Run]
Filename: "{app}\HaitooHubAgent\HaitooHubAgent.exe"; Parameters: "tray"; Description: "启动连接器并在 ERP 授权"; Flags: nowait postinstall skipifsilent
[Code]
function InitializeSetup(): Boolean;
var ExitCode: Integer;
begin
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -Command "if (Get-NetTCPConnection -LocalPort 45679 -State Listen -ErrorAction SilentlyContinue) { exit 1 }"',
    '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
  Result := Result and (ExitCode = 0);
  if not Result then MsgBox('请先退出正在运行的连接器，再安装。原设备授权与配置将保留。', mbInformation, MB_OK);
end;

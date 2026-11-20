#ifndef PayloadDir
  #error PayloadDir is required
#endif
#ifndef OutputDirPath
  #error OutputDirPath is required
#endif
[Setup]
AppId={{8DB23807-A886-46CB-8940-BD011724C3E0}
AppName=拾光 · 失物招领系统
AppVersion=1.1.1
AppVerName=拾光 · 失物招领系统 1.1.1
AppPublisher=拾光项目
DefaultDirName={localappdata}\Programs\ShiguangLostFound
DefaultGroupName=拾光失物招领系统
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDirPath}
OutputBaseFilename=Shiguang-Setup-1.1.1-x64
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=no
UninstallDisplayIcon={app}\Shiguang.exe
InfoBeforeFile={#PayloadDir}\安装说明.txt
[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: checkedonce
[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autodesktop}\拾光失物招领系统"; Filename: "{app}\Shiguang.exe"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{group}\拾光失物招领系统"; Filename: "{app}\Shiguang.exe"; WorkingDir: "{app}"
Name: "{group}\停止拾光系统"; Filename: "{app}\Shiguang.exe"; Parameters: "--stop"; WorkingDir: "{app}"
Name: "{group}\查看管理员账号"; Filename: "{app}\Shiguang.exe"; Parameters: "--admin"; WorkingDir: "{app}"
Name: "{group}\初始化测试数据"; Filename: "{app}\Shiguang.exe"; Parameters: "--demo"; WorkingDir: "{app}"
Name: "{group}\打开数据目录"; Filename: "{app}\Shiguang.exe"; Parameters: "--data"; WorkingDir: "{app}"
Name: "{group}\卸载拾光系统"; Filename: "{uninstallexe}"
[Run]
Filename: "{app}\Shiguang.exe"; Description: "启动拾光失物招领系统"; Flags: nowait postinstall skipifsilent
[UninstallRun]
Filename: "{app}\Shiguang.exe"; Parameters: "--stop --quiet"; Flags: runhidden waituntilterminated skipifdoesntexist; RunOnceId: "StopShiguang"
[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExitCode: Integer;
  Launcher: String;
begin
  Result := '';
  Launcher := ExpandConstant('{app}\Shiguang.exe');
  if FileExists(Launcher) then
    if not Exec(Launcher, '--stop --quiet', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ExitCode) or (ExitCode <> 0) then
      Result := '无法停止已安装的拾光服务。请先从开始菜单停止系统，再重新安装。';
end;

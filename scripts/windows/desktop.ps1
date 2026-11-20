param(
    [ValidateSet('Start','Stop','Data','Admin','Demo')][string]$Action = 'Start',
    [int]$Port = 8080,
    [int]$AiPort = 8765,
    [string]$DataHome = '',
    [string]$ErrorFile = '',
    [switch]$NoBrowser,
    [switch]$NoUI
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$appDirectory = Split-Path -Parent $PSScriptRoot
if (-not $DataHome) { $DataHome = Join-Path $env:LOCALAPPDATA 'ShiguangLostFound' }
$DataHome = [IO.Path]::GetFullPath($DataHome)
$runDirectory = Join-Path $DataHome 'runtime'
$dataDirectory = Join-Path $DataHome 'data'
$recordPath = Join-Path $runDirectory 'processes.json'
$operationLock = $null
$lockOwned = $false

function Read-Records {
    if (Test-Path -LiteralPath $recordPath) {
        $parsedRecords = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($parsedEntry in $parsedRecords) { Write-Output $parsedEntry }
        return
    }
    return @()
}
function Find-RecordedProcess($entry) {
    $candidate = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
    if (-not $candidate) { return $null }
    if ($candidate.StartTime.ToUniversalTime().ToString('o') -ne $entry.started) { return $null }
    $details = Get-CimInstance Win32_Process -Filter "ProcessId=$($entry.pid)"
    if (-not $details -or -not $details.CommandLine) { throw '无法核对后台服务身份，请稍后重试。' }
    if (-not $details.CommandLine.Contains($entry.marker)) { throw '后台记录与实际进程不一致，已停止操作。' }
    return $candidate
}
function Stop-RecordedServices {
    $records = @(Read-Records)
    foreach ($entry in $records) {
        $candidate = Find-RecordedProcess $entry
        if ($candidate) {
            Stop-Process -Id $candidate.Id -ErrorAction Stop
            if (-not $candidate.WaitForExit(15000)) { throw '服务未能及时停止，请稍后重试。' }
        }
    }
    if (Test-Path -LiteralPath $recordPath) { Remove-Item -LiteralPath $recordPath }
}
function Request-Health([int]$ListenPort) {
    try { return Invoke-RestMethod -Uri "http://127.0.0.1:$ListenPort/api/health" -TimeoutSec 2 }
    catch { return $null }
}
function Open-Website {
    if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port" }
}
function Assert-PortAvailable([int]$ListenPort) {
    $probe = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $ListenPort)
    try { $probe.Start() }
    catch { throw "端口 $ListenPort 正在被其他程序使用。请先关闭占用该端口的程序，再启动拾光。" }
    finally { $probe.Stop() }
}
try {
    New-Item -ItemType Directory -Force -Path $runDirectory,$dataDirectory | Out-Null
    if ($Action -eq 'Data') { Invoke-Item -LiteralPath $DataHome; exit 0 }
    if ($Action -eq 'Admin') {
        $credentials = Join-Path $dataDirectory 'admin-credentials.txt'
        if (-not (Test-Path -LiteralPath $credentials)) { throw '请先启动系统，首次启动后会自动生成管理员账号。' }
        Invoke-Item -LiteralPath $credentials
        exit 0
    }
    $hashProvider = [Security.Cryptography.SHA256]::Create()
    try {
        $hash = [BitConverter]::ToString($hashProvider.ComputeHash([Text.Encoding]::UTF8.GetBytes($DataHome.ToLowerInvariant()))).Replace('-','')
    } finally { $hashProvider.Dispose() }
    $operationLock = New-Object Threading.Mutex($false, "Local\ShiguangLostFound-$hash")
    try { $lockOwned = $operationLock.WaitOne(180000) }
    catch [Threading.AbandonedMutexException] { $lockOwned = $true }
    if (-not $lockOwned) { throw '另一个启动或停止操作尚未完成，请稍后重试。' }
    if ($Action -eq 'Demo') {
        $pythonPath = Join-Path $appDirectory 'python\python.exe'
        $seedPath = Join-Path $PSScriptRoot 'seed_demo.py'
        if (-not (Test-Path -LiteralPath $pythonPath) -or -not (Test-Path -LiteralPath $seedPath)) {
            throw '测试数据初始化工具缺失，请安装最新版本。'
        }
        if (-not (Test-Path -LiteralPath (Join-Path $dataDirectory 'lostfound.db'))) {
            throw '请先启动一次拾光系统，再初始化测试数据。'
        }
        $seedResult = & $pythonPath -I -B $seedPath --data-dir $dataDirectory 2>&1
        if ($LASTEXITCODE -ne 0) { throw ($seedResult -join [Environment]::NewLine) }
        Write-Output ($seedResult -join [Environment]::NewLine)
        exit 0
    }
    if ($Action -eq 'Stop') {
        Stop-RecordedServices
        Write-Output '拾光系统已停止。'
        exit 0
    }
    $records = @(Read-Records)
    $running = @($records | Where-Object { Find-RecordedProcess $_ })
    if ($running.Count -gt 0) {
        $health = Request-Health $Port
        $aiHealthy = $false
        try { $aiHealthy = (Invoke-RestMethod -Uri "http://127.0.0.1:$AiPort/health" -TimeoutSec 2).ok } catch {}
        if ($running.Count -eq 2 -and $health.ok -and $health.ai -and $aiHealthy) {
            Open-Website
            Write-Output '拾光系统已经启动。'
            exit 0
        }
        throw '拾光后台尚未就绪。请先使用“停止拾光系统”，再重新启动。'
    }
    Assert-PortAvailable $Port
    Assert-PortAvailable $AiPort
    $javaPath = Join-Path $appDirectory 'java\bin\java.exe'
    $pythonPath = Join-Path $appDirectory 'python\python.exe'
    if (-not (Test-Path -LiteralPath $javaPath) -or -not (Test-Path -LiteralPath $pythonPath)) {
        throw '运行环境不完整，请重新安装拾光系统。'
    }
    $newRecords = @()
    try {
        $aiArguments = @('-I','-B','-m','uvicorn','ai.service:app','--app-dir',('"' + $appDirectory + '"'),'--host','127.0.0.1','--port',"$AiPort",'--no-access-log')
        $aiProcess = Start-Process -FilePath $pythonPath -ArgumentList $aiArguments -WorkingDirectory $DataHome -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runDirectory 'ai.out.log') -RedirectStandardError (Join-Path $runDirectory 'ai.err.log')
        $newRecords += @{pid=$aiProcess.Id;kind='ai';started=$aiProcess.StartTime.ToUniversalTime().ToString('o');marker=$appDirectory}
        ConvertTo-Json -InputObject @($newRecords) | Set-Content -LiteralPath $recordPath -Encoding UTF8
        $classPath = (Join-Path $appDirectory 'app.jar') + ';' + (Join-Path $appDirectory 'lib\*')
        $javaArguments = @(('"-Dapp.data=' + $dataDirectory + '"'),"-Dapp.port=$Port","-Dapp.ai=http://127.0.0.1:$AiPort",'-cp',('"' + $classPath + '"'),'cn.campus.lostfound.Server')
        $webProcess = Start-Process -FilePath $javaPath -ArgumentList $javaArguments -WorkingDirectory $DataHome -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runDirectory 'web.out.log') -RedirectStandardError (Join-Path $runDirectory 'web.err.log')
        $newRecords += @{pid=$webProcess.Id;kind='web';started=$webProcess.StartTime.ToUniversalTime().ToString('o');marker=$dataDirectory}
        ConvertTo-Json -InputObject @($newRecords) | Set-Content -LiteralPath $recordPath -Encoding UTF8
        $ready = $false
        $deadline = [DateTime]::UtcNow.AddSeconds(180)
        while ([DateTime]::UtcNow -lt $deadline) {
            Start-Sleep -Milliseconds 750
            if ($aiProcess.HasExited) { throw 'AI 服务启动失败。请查看数据目录 runtime 中的 ai.err.log。' }
            if ($webProcess.HasExited) { throw '网站启动失败。请查看数据目录 runtime 中的 web.err.log。' }
            $health = Request-Health $Port
            if ($health.ok -and $health.ai) {
                $aiHealth = $null
                try { $aiHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$AiPort/health" -TimeoutSec 2 } catch {}
                if ($aiHealth.ok) { $ready = $true; break }
            }
        }
        if (-not $ready) { throw '启动超过三分钟，请检查数据目录 runtime 中的日志。' }
        Open-Website
        Write-Output '拾光系统已启动，AI 语义检索已连接。'
    } catch {
        $failure = $_
        foreach ($entry in $newRecords) {
            try { $candidate = Find-RecordedProcess $entry; if ($candidate) { Stop-Process -Id $candidate.Id -ErrorAction Stop } } catch {}
        }
        if (Test-Path -LiteralPath $recordPath) { Remove-Item -LiteralPath $recordPath }
        throw $failure
    }
} catch {
    $message = $_.Exception.Message
    if ($ErrorFile) { try { [IO.File]::WriteAllText($ErrorFile, $message, (New-Object Text.UTF8Encoding($false))) } catch {} }
    [Console]::Error.WriteLine($message)
    if (-not $NoUI) {
        Add-Type -AssemblyName System.Windows.Forms
        [Windows.Forms.MessageBox]::Show($message,'拾光 · 失物招领系统',[Windows.Forms.MessageBoxButtons]::OK,[Windows.Forms.MessageBoxIcon]::Error) | Out-Null
    }
    exit 1
} finally {
    if ($lockOwned) { $operationLock.ReleaseMutex() }
    if ($operationLock) { $operationLock.Dispose() }
}

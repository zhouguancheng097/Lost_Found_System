param([int]$Port = 8080, [int]$AiPort = 8765, [switch]$WithoutAI, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$runtimeDirectory = Join-Path $projectRoot 'runtime'
New-Item -ItemType Directory -Force -Path $runtimeDirectory | Out-Null
$recordFile = Join-Path $runtimeDirectory 'processes.json'
function Open-SystemPage {
    if ($NoBrowser) { return }
    try { Start-Process -FilePath "http://127.0.0.1:$Port" -ErrorAction Stop | Out-Null }
    catch { Write-Warning "Website is ready, but the browser could not open. Visit http://127.0.0.1:$Port" }
}
if (Test-Path -LiteralPath $recordFile) {
    $records = Get-Content -Raw -LiteralPath $recordFile | ConvertFrom-Json
    $runningRecords = @()
    foreach ($record in $records) {
        $recordedProcess = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
        if ($recordedProcess -and $recordedProcess.StartTime.ToUniversalTime().ToString('o') -eq $record.started) { $runningRecords += $record }
    }
    if ($runningRecords.Count -gt 0) {
        $existingHealth = $null
        try { $existingHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 3 } catch {}
        if (($runningRecords.kind -contains 'web') -and $existingHealth.ok -and ($WithoutAI -or $existingHealth.ai)) {
            Write-Output "Website is already ready: http://127.0.0.1:$Port"
            Open-SystemPage
            return
        }
        throw 'Some project services are running but not ready. Run scripts/stop.ps1, then start again.'
    }
}
if (-not (Test-Path -LiteralPath "$projectRoot\target\classes\cn\campus\lostfound\Server.class")) { throw 'Build the project first: scripts/build.ps1' }
$newRecords = @()
try {
    if (-not $WithoutAI) {
        $pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create .venv and download the model first. See README.md.' }
        $ai = Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','ai.service:app','--host','127.0.0.1','--port',"$AiPort",'--no-access-log') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput "$runtimeDirectory\ai.out.log" -RedirectStandardError "$runtimeDirectory\ai.err.log"
        $newRecords += @{pid=$ai.Id;kind='ai';started=$ai.StartTime.ToUniversalTime().ToString('o')}
    }
    $javaPath = (Get-Command java.exe).Source
    $classpath = "$projectRoot\target\classes;$projectRoot\target\dependency\*"
    $web = Start-Process -FilePath $javaPath -ArgumentList @("-Dapp.port=$Port","-Dapp.ai=http://127.0.0.1:$AiPort",'-cp',('"'+$classpath+'"'),'cn.campus.lostfound.Server') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput "$runtimeDirectory\web.out.log" -RedirectStandardError "$runtimeDirectory\web.err.log"
    $newRecords += @{pid=$web.Id;kind='web';started=$web.StartTime.ToUniversalTime().ToString('o')}
    ConvertTo-Json -InputObject $newRecords | Set-Content -Encoding UTF8 -LiteralPath $recordFile
    $ready = $false
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        Start-Sleep -Seconds 1
        if ($web.HasExited) { throw 'Website process exited. See runtime/web.err.log.' }
        try { $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 3; if ($health.ok -and ($WithoutAI -or $health.ai)) { $ready = $true; break } } catch {}
    }
    if (-not $ready) { throw 'Service readiness timed out. See runtime logs.' }
    Write-Output "Website ready: http://127.0.0.1:$Port"
    Write-Output "Admin credentials: $projectRoot\data\admin-credentials.txt"
} catch {
    foreach ($record in $newRecords) { Stop-Process -Id $record.pid -ErrorAction SilentlyContinue }
    throw
}
Open-SystemPage

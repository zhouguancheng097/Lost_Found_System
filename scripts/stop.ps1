$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$recordFile = Join-Path $projectRoot 'runtime\processes.json'
if (-not (Test-Path -LiteralPath $recordFile)) { Write-Output 'No recorded services.'; exit }
$records = Get-Content -Raw -LiteralPath $recordFile | ConvertFrom-Json
foreach ($record in $records) {
    $process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    if ($process.StartTime.ToUniversalTime().ToString('o') -ne $record.started) { throw 'PID was reused. Refusing to stop an unrelated process.' }
    $details = Get-CimInstance Win32_Process -Filter "ProcessId=$($record.pid)"
    $expected = if ($record.kind -eq 'web') { 'cn.campus.lostfound.Server' } else { 'ai.service:app' }
    if (-not $details.CommandLine.Contains($expected)) { throw 'Process does not match this project.' }
    Stop-Process -Id $record.pid
}
Remove-Item -LiteralPath $recordFile
Write-Output 'Project services stopped.'

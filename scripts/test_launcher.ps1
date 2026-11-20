$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$recordFile = Join-Path $projectRoot 'runtime\processes.json'
if (-not (Test-Path -LiteralPath $recordFile)) { throw 'Start the system with -NoBrowser before running this test.' }
$before = Get-Content -Raw -LiteralPath $recordFile
$global:launcherTestUrl = $null
function Start-Process {
    [CmdletBinding()]
    param([string]$FilePath)
    if ($FilePath -ne 'http://127.0.0.1:8080') { throw 'Unexpected process creation during repeated startup.' }
    $global:launcherTestUrl = $FilePath
}
& (Join-Path $PSScriptRoot 'start.ps1')
if ($global:launcherTestUrl -ne 'http://127.0.0.1:8080') { throw 'Startup did not request the expected browser URL.' }
if ((Get-Content -Raw -LiteralPath $recordFile) -ne $before) { throw 'Repeated startup changed the process records.' }
function Start-Process {
    [CmdletBinding()]
    param([string]$FilePath)
    throw 'Simulated browser launch failure.'
}
& (Join-Path $PSScriptRoot 'start.ps1')
$health = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/health' -TimeoutSec 5
if (-not $health.ok -or -not $health.ai) { throw 'Browser failure affected healthy services.' }
if ((Get-Content -Raw -LiteralPath $recordFile) -ne $before) { throw 'Browser failure changed the process records.' }
Write-Output 'PASS: repeated startup requests the browser URL without creating duplicate services.'
Write-Output 'PASS: a browser launch failure leaves the website and model running.'

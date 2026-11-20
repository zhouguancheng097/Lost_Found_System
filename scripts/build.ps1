param([switch]$SkipTests)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$mavenCommand = Get-Command mvn.cmd -ErrorAction SilentlyContinue
if ($mavenCommand) { $mavenPath = $mavenCommand.Source }
else {
    $mavenPath = Get-ChildItem -Path 'D:\JAVA_software\*\plugins\maven\lib\maven3\bin\mvn.cmd', "$projectRoot\tools\apache-maven-*\bin\mvn.cmd" -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $mavenPath) { throw 'Maven not found. Install Maven 3.9+ and add it to PATH.' }
$buildArguments = @("-Dmaven.repo.local=$projectRoot\.m2", '-B', '-ntp', 'package')
if ($SkipTests) { $buildArguments += '-DskipTests' }
& $mavenPath @buildArguments
if ($LASTEXITCODE -ne 0) { throw 'Build failed. See Maven output.' }

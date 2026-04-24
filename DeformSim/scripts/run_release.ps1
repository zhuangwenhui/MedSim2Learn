param(
    [string]$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path,
    [string]$BuildDir = (Join-Path (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path 'build')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
    throw "ProjectRoot not found: $ProjectRoot"
}

$setupEnvPath = Join-Path $ProjectRoot 'scripts\setup_env.ps1'
if (-not (Test-Path -LiteralPath $setupEnvPath -PathType Leaf)) {
    throw "setup_env.ps1 not found: $setupEnvPath"
}

. "$setupEnvPath" -ProjectRoot $ProjectRoot -BuildType 'Release'

$exePath = Join-Path $BuildDir 'LVBasicFramework.exe'
if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
    throw "Executable not found: $exePath"
}

Push-Location $ProjectRoot
try {
    Write-Output "Running $exePath"
    Write-Output "WorkingDirectory=$ProjectRoot"
    & $exePath
    if ($LASTEXITCODE -ne 0) {
        throw "LVBasicFramework.exe exited with code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

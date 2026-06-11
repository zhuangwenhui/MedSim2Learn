param(
    [string]$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path,
    [string]$BuildDir = (Join-Path (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path 'build'),
    # The exe writes ./DeformedSample_* relative to CWD; land it under DataFlow,
    # not inside the DeformSim source tree.
    [string]$OutDir = (Join-Path (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path 'DataFlow\DeformSim\scratch')
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

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Push-Location $OutDir
try {
    Write-Output "Running $exePath"
    Write-Output "WorkingDirectory=$OutDir"
    & $exePath
    if ($LASTEXITCODE -ne 0) {
        throw "LVBasicFramework.exe exited with code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

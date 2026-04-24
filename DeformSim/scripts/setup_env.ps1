param(
    [string]$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path,
    [string]$BuildType = 'Release',
    [string]$VsDevCmdPath = '',
    [string]$MklBin = 'C:\Program Files (x86)\Intel\oneAPI\mkl\latest\bin',
    [string]$CompilerBin = 'C:\Program Files (x86)\Intel\oneAPI\compiler\latest\bin',
    [string]$MklLib = 'C:\Program Files (x86)\Intel\oneAPI\mkl\latest\lib',
    [string]$CompilerLib = 'C:\Program Files (x86)\Intel\oneAPI\compiler\latest\lib'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Import-BatchEnvironment {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BatchFile
    )

    $batchCommand = '"' + $BatchFile + '" -no_logo -arch=x64 -host_arch=x64 >nul 2>&1 && set'
    $output = & cmd.exe /c $batchCommand

    foreach ($line in $output) {
        $index = $line.IndexOf('=')
        if ($index -le 0) {
            continue
        }

        $name = $line.Substring(0, $index)
        $value = $line.Substring($index + 1)
        Set-Item -Path "Env:$name" -Value $value
    }
}

function Assert-RequiredDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Label not found: $Path"
    }

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "$Label is not a directory: $Path"
    }
}

function Assert-RequiredFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Label not found: $Path"
    }

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label is not a file: $Path"
    }
}

function Get-VsDevCmdPath {
    param(
        [string]$ConfiguredPath
    )

    if ($ConfiguredPath) {
        Assert-RequiredFile -Path $ConfiguredPath -Label 'VsDevCmdPath'
        return $ConfiguredPath
    }

    $vswherePath = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path -LiteralPath $vswherePath -PathType Leaf) {
        $resolvedPath = & $vswherePath -version '[17.0,18.0)' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -find 'Common7\Tools\VsDevCmd.bat' | Select-Object -First 1
        if ($resolvedPath) {
            return $resolvedPath.Trim()
        }
    }

    foreach ($edition in @('Community', 'Professional', 'Enterprise', 'BuildTools')) {
        $vsRoot = 'C:\Program Files\Microsoft Visual Studio\2022'
        if ($edition -eq 'BuildTools') {
            $vsRoot = 'C:\Program Files (x86)\Microsoft Visual Studio\2022'
        }

        $candidate = Join-Path $vsRoot "$edition\Common7\Tools\VsDevCmd.bat"
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }

    throw 'VsDevCmd.bat not found. Install Visual Studio 2022 or pass -VsDevCmdPath explicitly.'
}

function Get-CMakeBinPath {
    $cmakeCommand = Get-Command cmake.exe -ErrorAction SilentlyContinue
    if ($cmakeCommand) {
        return Split-Path -Parent $cmakeCommand.Source
    }

    if ($env:VSINSTALLDIR) {
        $vsCMakeBin = Join-Path $env:VSINSTALLDIR 'Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin'
        if (Test-Path -LiteralPath (Join-Path $vsCMakeBin 'cmake.exe') -PathType Leaf) {
            return $vsCMakeBin
        }
    }

    foreach ($candidate in @(
        'C:\Program Files\CMake\bin'
    )) {
        if (Test-Path -LiteralPath (Join-Path $candidate 'cmake.exe') -PathType Leaf) {
            return $candidate
        }
    }

    throw 'cmake.exe not found in PATH or common Visual Studio/CMake locations.'
}

function Normalize-PathValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    return $Path.Trim().Trim('"').TrimEnd('\')
}

function Update-EnvironmentPrefix {
    param(
        [Parameter(Mandatory = $true)]
        [string]$VariableName,
        [Parameter(Mandatory = $true)]
        [string[]]$PrefixEntries
    )

    $remainingEntries = @()
    $currentValue = [System.Environment]::GetEnvironmentVariable($VariableName)
    if ($currentValue) {
        $remainingEntries = $currentValue -split ';' | Where-Object { $_ -and $_.Trim() -ne '' }
    }

    $normalizedPrefix = $PrefixEntries | ForEach-Object { Normalize-PathValue -Path $_ }
    $filteredEntries = foreach ($entry in $remainingEntries) {
        $normalizedEntry = Normalize-PathValue -Path $entry
        if ($normalizedPrefix -notcontains $normalizedEntry) {
            $entry
        }
    }

    Set-Item -Path "Env:$VariableName" -Value (($PrefixEntries + $filteredEntries) -join ';')
}

Assert-RequiredDirectory -Path $ProjectRoot -Label 'ProjectRoot'
Assert-RequiredDirectory -Path $MklBin -Label 'MklBin'
Assert-RequiredDirectory -Path $CompilerBin -Label 'CompilerBin'
Assert-RequiredDirectory -Path $MklLib -Label 'MklLib'
Assert-RequiredDirectory -Path $CompilerLib -Label 'CompilerLib'

$VsDevCmdPath = Get-VsDevCmdPath -ConfiguredPath $VsDevCmdPath
Import-BatchEnvironment -BatchFile $VsDevCmdPath

if (-not $env:VSINSTALLDIR -or -not $env:VSCMD_VER) {
    throw 'Visual Studio environment import failed.'
}

$CMakeBin = Get-CMakeBinPath
Update-EnvironmentPrefix -VariableName 'PATH' -PrefixEntries @($CMakeBin, $MklBin, $CompilerBin)
Update-EnvironmentPrefix -VariableName 'LIB' -PrefixEntries @($CompilerLib, $MklLib)
$env:CC = 'cl.exe'
$env:CXX = 'cl.exe'

if (-not $env:SIM2LEARN_PARAM_NUM_THREADS) {
    $env:SIM2LEARN_PARAM_NUM_THREADS = '16'
}

if (-not $env:SIM2LEARN_PARAM_MKL_NUM_THREADS) {
    $env:SIM2LEARN_PARAM_MKL_NUM_THREADS = '1'
}

$env:DEFORMSIM_PROJECT_ROOT = $ProjectRoot
$env:DEFORMSIM_BUILD_TYPE = $BuildType
$env:DEFORMSIM_VSDEVCMD_PATH = $VsDevCmdPath

$isDotSourced = $MyInvocation.InvocationName -eq '.'
if (-not $isDotSourced) {
    Write-Output 'DeformSim environment prepared.'
    Write-Output "ProjectRoot=$ProjectRoot"
    Write-Output "BuildType=$BuildType"
    Write-Output "VsDevCmdPath=$VsDevCmdPath"
    Write-Output "MklBin=$MklBin"
    Write-Output "CompilerBin=$CompilerBin"
    Write-Output "MklLib=$MklLib"
    Write-Output "CompilerLib=$CompilerLib"
    Write-Output "SIM2LEARN_PARAM_NUM_THREADS=$env:SIM2LEARN_PARAM_NUM_THREADS"
    Write-Output "SIM2LEARN_PARAM_MKL_NUM_THREADS=$env:SIM2LEARN_PARAM_MKL_NUM_THREADS"
}

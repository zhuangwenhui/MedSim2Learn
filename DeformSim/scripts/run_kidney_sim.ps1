<#
.SYNOPSIS
    Run the DeformSim kidney force-deformation simulation with a bounded,
    literature-grounded contact-force band, writing deformed samples into a
    caller-chosen output directory.

.DESCRIPTION
    Thin wrapper around the DeformSim Release executable. It sources
    setup_env.ps1 (Intel oneAPI MKL/compiler runtime on PATH), sets the
    SIM2LEARN_PARAM_* force/contact environment variables, and launches the
    exe from inside -OutputDir so the run's "./DeformedSample_ComplexObject_*"
    folder and SampleID CSV land there (the exe always writes relative to its
    current working directory).

    The script has two mutually exclusive modes. In sampling mode (default),
    force vectors are sampled uniformly in [FORCE_*_MIN, FORCE_*_MAX] and kept
    only if their angle from the global -z axis lies in
    [MIN_ANGLE_DEG, MAX_ANGLE_DEG]; set the Z band negative to press into the
    table. In exact-replay mode (-ForceListCsv set), the exe reads per-frame
    forces from that CSV (SIM2LEARN_PARAM_FORCE_LIST_CSV) and ignores the
    sampling bands. Material parameters are left at DeformSim defaults unless
    overridden.

.NOTES
    Author/committer: WENHUIZ <84453228+zhuangwenhui@users.noreply.github.com>
#>
param(
    [Parameter(Mandatory = $true)] [string]$PlyPath,
    [Parameter(Mandatory = $true)] [string]$AnnotationPath,
    [Parameter(Mandatory = $true)] [string]$OutputDir,
    [int]$NumVector = 2,
    [int]$Seed = 20260530,
    [double]$ForceXMin = -2.0, [double]$ForceXMax = 2.0,
    [double]$ForceYMin = -2.0, [double]$ForceYMax = 2.0,
    [double]$ForceZMin = -6.0, [double]$ForceZMax = -2.0,
    [double]$MinAngleDeg = 0.0, [double]$MaxAngleDeg = 40.0,
    [int]$NumThreads = 2,
    # Exact-replay mode: when set, the exe reads per-frame forces from this CSV
    # (SIM2LEARN_PARAM_FORCE_LIST_CSV) and ignores the sampling FORCE/angle bands.
    # When empty (default), the script runs in sampling mode (the bands above).
    [string]$ForceListCsv = '',
    # Optional explicit MKL thread cap; 0 => leave setup_env.ps1 default.
    [int]$MklNumThreads = 0,
    # Optional material overrides; null => leave DeformSim defaults.
    [Nullable[double]]$MaterialYoung = $null,
    [Nullable[double]]$MaterialPoisson = $null,
    [string]$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path,
    # Out-of-tree build location for this workspace layout.
    [string]$ExePath = ''
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

# Resolve the executable. Default to the out-of-tree CMake Release output
# (sibling build/ per the workspace convention), then fall back to the
# in-tree build/ that run_release.ps1 assumes.
if (-not $ExePath) {
    $candidates = @(
        (Join-Path $ProjectRoot '..\build\DeformSim\vs2022-x64\Release\LVBasicFramework.exe'),
        (Join-Path $ProjectRoot 'build\LVBasicFramework.exe')
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c -PathType Leaf) { $ExePath = (Resolve-Path -LiteralPath $c).Path; break }
    }
}
if (-not $ExePath -or -not (Test-Path -LiteralPath $ExePath -PathType Leaf)) {
    throw "LVBasicFramework.exe not found. Pass -ExePath explicitly."
}

$resolvedPly = (Resolve-Path -LiteralPath $PlyPath).Path
$resolvedAnnotation = (Resolve-Path -LiteralPath $AnnotationPath).Path

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$resolvedOut = (Resolve-Path -LiteralPath $OutputDir).Path

. "$setupEnvPath" -ProjectRoot $ProjectRoot -BuildType 'Release'

# Always-set inputs (shared by both modes).
$env:SIM2LEARN_PARAM_PLY_PATH = $resolvedPly
$env:SIM2LEARN_PARAM_ANNOTATION_PATH = $resolvedAnnotation
$env:SIM2LEARN_PARAM_SEED = "$Seed"
$env:SIM2LEARN_PARAM_NUM_THREADS = "$NumThreads"
if ($MaterialYoung -ne $null) { $env:SIM2LEARN_PARAM_MATERIAL_YOUNG = "$MaterialYoung" }
if ($MaterialPoisson -ne $null) { $env:SIM2LEARN_PARAM_MATERIAL_POISSON = "$MaterialPoisson" }
if ($MklNumThreads -gt 0) { $env:SIM2LEARN_PARAM_MKL_NUM_THREADS = "$MklNumThreads" }

$replayMode = [bool]$ForceListCsv
if ($replayMode) {
    # Exact-replay mode: feed the per-frame force CSV; the exe ignores the
    # sampling FORCE_*_MIN/MAX and MIN/MAX_ANGLE_DEG bands here.
    $resolvedForceList = (Resolve-Path -LiteralPath $ForceListCsv).Path
    $env:SIM2LEARN_PARAM_FORCE_LIST_CSV = $resolvedForceList
}
else {
    # Sampling mode: random force vectors in the bands, angle-gated from -z.
    $env:SIM2LEARN_PARAM_NUM_VECTOR = "$NumVector"
    $env:SIM2LEARN_PARAM_FORCE_X_MIN = "$ForceXMin"
    $env:SIM2LEARN_PARAM_FORCE_X_MAX = "$ForceXMax"
    $env:SIM2LEARN_PARAM_FORCE_Y_MIN = "$ForceYMin"
    $env:SIM2LEARN_PARAM_FORCE_Y_MAX = "$ForceYMax"
    $env:SIM2LEARN_PARAM_FORCE_Z_MIN = "$ForceZMin"
    $env:SIM2LEARN_PARAM_FORCE_Z_MAX = "$ForceZMax"
    $env:SIM2LEARN_PARAM_MIN_ANGLE_DEG = "$MinAngleDeg"
    $env:SIM2LEARN_PARAM_MAX_ANGLE_DEG = "$MaxAngleDeg"
}

Write-Output "Exe:        $ExePath"
Write-Output "PLY:        $resolvedPly"
Write-Output "Annotation: $resolvedAnnotation"
Write-Output "OutputDir:  $resolvedOut"
if ($replayMode) {
    Write-Output "Mode: replay (force list = $resolvedForceList)"
}
else {
    Write-Output "NumVector:  $NumVector  Seed: $Seed"
    Write-Output "Force X:    [$ForceXMin, $ForceXMax]  Y: [$ForceYMin, $ForceYMax]  Z: [$ForceZMin, $ForceZMax]"
    Write-Output "Angle band: [$MinAngleDeg, $MaxAngleDeg] deg from -z"
}

Push-Location $resolvedOut
try {
    & $ExePath
    $exit = $LASTEXITCODE
    Write-Output "=== DeformSim exit code: $exit ==="
    if ($exit -ne 0) {
        throw "LVBasicFramework.exe exited with code $exit"
    }
}
finally {
    Pop-Location
}

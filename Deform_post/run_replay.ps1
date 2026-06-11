<#
.SYNOPSIS
    End-to-end kidney digital-twin force-replay: prep -> DeformSim exact replay
    -> render -> serialize, from a real per-frame sensor-force sequence.

.DESCRIPTION
    Python (kidney_replay.py) stays pure: it builds forces_model.csv (the exact
    per-frame model forces for SIM2LEARN_PARAM_FORCE_LIST_CSV), labels.csv (the
    real sensor Newtons used as supervision), a single fixed laparoscope camera,
    and replay_meta.json. This script owns the only MKL-aware step: it sources
    DeformSim/scripts/setup_env.ps1 (Intel oneAPI runtime on PATH) and launches
    the Release exe in exact-replay mode from inside the sim output dir (the exe
    writes "./DeformedSample_ComplexObject_*" relative to its CWD), mirroring
    run_kidney_sim.ps1. Then it renders one PNG per deformed PLY with the fixed
    camera and serializes the vision-force pairs into a .pt dataset.

    Single-thread sims by default (-NumThreads 1, MKL 1). Material is fixed to
    the kidney decision E=0.03 MPa, v=0.49.

.NOTES
    Author/committer: WENHUIZ <84453228+zhuangwenhui@users.noreply.github.com>
#>
param(
    [Parameter(Mandatory = $true)] [string]$Seq,
    [Parameter(Mandatory = $true)] [string]$OutDir,
    [string]$RealDataRoot = 'D:\Image2Force Data\Real Visual-force Paired Data',
    [string]$MeshPath = 'D:\MedSim2Learn-ComplexObject\DataFlow\ShapeReconstruction\meshes\kidney_anat.ply',
    [string]$AnnotationPath = 'D:\MedSim2Learn-ComplexObject\DataFlow\Deform_post\annotations\kidney_anat_contact_k1.json',
    [Nullable[int]]$Subsample = $null,
    [double]$MaterialYoung = 0.03,
    [double]$MaterialPoisson = 0.49,
    [int]$NumThreads = 1,
    [string]$Python = 'C:/Users/space/anaconda3/envs/MedLearning/python.exe',
    [string]$DeformSimRoot = 'D:\MedSim2Learn-ComplexObject\DeformSim',
    [string]$ExePath = 'D:\MedSim2Learn-ComplexObject\build\DeformSim\vs2022-x64\Release\LVBasicFramework.exe'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot   # Deform_post (holds kidney_replay.py)
$ReplayPy = Join-Path $ScriptDir 'kidney_replay.py'
$RealCsv = Join-Path $RealDataRoot ("{0}.csv" -f $Seq)
$SetupEnv = Join-Path $DeformSimRoot 'scripts\setup_env.ps1'

foreach ($pair in @(@($ReplayPy, 'kidney_replay.py'), @($RealCsv, 'real CSV'),
                    @($MeshPath, 'mesh'), @($AnnotationPath, 'annotation'),
                    @($SetupEnv, 'setup_env.ps1'), @($ExePath, 'exe'))) {
    if (-not (Test-Path -LiteralPath $pair[0] -PathType Leaf)) {
        throw ("{0} not found: {1}" -f $pair[1], $pair[0])
    }
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$ResolvedOut = (Resolve-Path -LiteralPath $OutDir).Path
$SimDir = Join-Path $ResolvedOut 'sim'
$PngDir = Join-Path $ResolvedOut 'png'
$DataDir = Join-Path $ResolvedOut 'dataset'
New-Item -ItemType Directory -Force -Path $SimDir, $PngDir, $DataDir | Out-Null

$ForcesModel = Join-Path $ResolvedOut 'forces_model.csv'
$Labels = Join-Path $ResolvedOut 'labels.csv'
$Camera = Join-Path $ResolvedOut 'camera.json'

# --- Stage 1: prep (pure Python) ---
Write-Output '=== Stage 1: prep ==='
$prepArgs = @($ReplayPy, 'prep', '--real-csv', $RealCsv, '--mesh', $MeshPath,
              '--annotation', $AnnotationPath, '--out-dir', $ResolvedOut,
              '--young', "$MaterialYoung", '--poisson', "$MaterialPoisson")
if ($Subsample -ne $null) { $prepArgs += @('--subsample', "$Subsample") }
& $Python @prepArgs
if ($LASTEXITCODE -ne 0) { throw "prep failed (exit $LASTEXITCODE)" }

# --- Stage 2: DeformSim exact replay (MKL-aware; mirrors run_kidney_sim.ps1) ---
Write-Output '=== Stage 2: DeformSim exact replay ==='
. "$SetupEnv" -ProjectRoot $DeformSimRoot -BuildType 'Release'

$env:SIM2LEARN_PARAM_PLY_PATH = (Resolve-Path -LiteralPath $MeshPath).Path
$env:SIM2LEARN_PARAM_ANNOTATION_PATH = (Resolve-Path -LiteralPath $AnnotationPath).Path
$env:SIM2LEARN_PARAM_FORCE_LIST_CSV = (Resolve-Path -LiteralPath $ForcesModel).Path
$env:SIM2LEARN_PARAM_MATERIAL_YOUNG = "$MaterialYoung"
$env:SIM2LEARN_PARAM_MATERIAL_POISSON = "$MaterialPoisson"
$env:SIM2LEARN_PARAM_NUM_THREADS = "$NumThreads"
$env:SIM2LEARN_PARAM_MKL_NUM_THREADS = '1'

Write-Output "Exe:          $ExePath"
Write-Output "PLY:          $($env:SIM2LEARN_PARAM_PLY_PATH)"
Write-Output "Annotation:   $($env:SIM2LEARN_PARAM_ANNOTATION_PATH)"
Write-Output "ForceListCsv: $($env:SIM2LEARN_PARAM_FORCE_LIST_CSV)"
Write-Output "Material:     E=$MaterialYoung MPa, v=$MaterialPoisson"
Write-Output "Threads:      $NumThreads (MKL 1)"
Write-Output "SimDir:       $SimDir"

Push-Location $SimDir
try {
    & $ExePath
    $exit = $LASTEXITCODE
    Write-Output "=== DeformSim exit code: $exit ==="
    if ($exit -ne 0) { throw "LVBasicFramework.exe exited with code $exit" }
}
finally {
    Pop-Location
}

# Locate the timestamped DeformedSample dir the exe just wrote under $SimDir.
$DeformedDir = Get-ChildItem -LiteralPath $SimDir -Directory -Filter 'DeformedSample_ComplexObject*' |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $DeformedDir) { throw "no DeformedSample_ComplexObject* dir under $SimDir" }
$PlyDir = $DeformedDir.FullName
Write-Output "Deformed PLYs: $PlyDir"

# --- Stage 3: render (pure Python, fixed camera) ---
Write-Output '=== Stage 3: render ==='
& $Python $ReplayPy render --ply-dir $PlyDir --camera $Camera --out-png-dir $PngDir
if ($LASTEXITCODE -ne 0) { throw "render failed (exit $LASTEXITCODE)" }

# --- Stage 4: serialize (pure Python; reuses sim2vfp.DataPreprocessor) ---
# DataPreprocessor wants exactly one CSV (labels.csv) in the dataset dir and
# pairs PNG stem == SampleID. labels.csv lives in $ResolvedOut, which must hold
# no other CSV; forces_model.csv is intentionally kept there too, so copy
# labels.csv into an isolated dir for serialization.
Write-Output '=== Stage 4: serialize ==='
$LabelDir = Join-Path $ResolvedOut 'labels_only'
New-Item -ItemType Directory -Force -Path $LabelDir | Out-Null
Copy-Item -LiteralPath $Labels -Destination (Join-Path $LabelDir 'labels.csv') -Force
# Resize to 224x224 so production .pt are ~1 GB/seq (raw 800px float32 was ~13 GB/seq).
& $Python $ReplayPy serialize --png-dir $PngDir --labels (Join-Path $LabelDir 'labels.csv') --out-data-dir $DataDir --resize 224
if ($LASTEXITCODE -ne 0) { throw "serialize failed (exit $LASTEXITCODE)" }

Write-Output ''
Write-Output '=== Replay complete ==='
Write-Output "OutDir:  $ResolvedOut"
Write-Output "PLYs:    $PlyDir"
Write-Output "PNGs:    $PngDir"
Write-Output "Dataset: $DataDir"

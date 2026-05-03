<#
.SYNOPSIS
Generate a FEM pressure comparison matrix for one .mvr input across
multiple ShapeReconstruction algorithm configurations.

.DESCRIPTION
Runs mvr_to_mesh_cli for each candidate (direct, --adaptive-remesh
variants, --cgal-mesh variants), then check_fem_pressure --matrix
to aggregate a Markdown report.

.PARAMETER InputMvr
Path to input .mvr file.

.PARAMETER OutDir
Output directory for intermediate .ply and final pressure_matrix.md.

.PARAMETER CliExe
Path to mvr_to_mesh_cli executable.

.PARAMETER PressureExe
Path to check_fem_pressure executable.

.PARAMETER BaselinePly
Optional path to plate.ply for baseline comparison row.

.PARAMETER NSamples
DeformSim sample count (default 22500 = Center Pattern default).
#>

param(
    [Parameter(Mandatory=$true)]  [string]$InputMvr,
    [Parameter(Mandatory=$true)]  [string]$OutDir,
    [Parameter(Mandatory=$true)]  [string]$CliExe,
    [Parameter(Mandatory=$true)]  [string]$PressureExe,
    [Parameter(Mandatory=$false)] [string]$BaselinePly = "",
    [Parameter(Mandatory=$false)] [int]   $NSamples   = 22500
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $InputMvr)) {
    Write-Error "Input MVR not found: $InputMvr"
    exit 1
}
if (-not (Test-Path $CliExe)) {
    Write-Error "CLI exe not found: $CliExe"
    exit 1
}
if (-not (Test-Path $PressureExe)) {
    Write-Error "Pressure exe not found: $PressureExe"
    exit 1
}

New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

# Hardcoded candidate list. Edit to change matrix scope.
$candidates = @(
    @{ Name="direct";          Args=@() }
    @{ Name="adaptive_iter1";  Args=@("--adaptive-remesh") }
    @{ Name="adaptive_iter3";  Args=@("--adaptive-remesh","--adaptive-iterations","3") }
    @{ Name="cgal_default";    Args=@("--cgal-mesh") }
    @{ Name="cgal_L005";       Args=@("--cgal-mesh","--target-edge-length","0.05") }
    @{ Name="cgal_L010";       Args=@("--cgal-mesh","--target-edge-length","0.10") }
)

$plyArgs = @()
$labelArgs = @()
$failedCandidates = @()

foreach ($c in $candidates) {
    $outBase = Join-Path $OutDir $c.Name
    $cliArgs = @($InputMvr, "-o", $outBase) + $c.Args
    Write-Host "[run] mvr_to_mesh_cli $($c.Name): $($c.Args -join ' ')"
    & $CliExe @cliArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "[$($c.Name)] mvr_to_mesh_cli failed (exit=$LASTEXITCODE) -- skipping candidate"
        $failedCandidates += $c.Name
        continue
    }
    $plyPath = "$outBase.ply"
    if (-not (Test-Path $plyPath)) {
        Write-Warning "[$($c.Name)] expected $plyPath but not produced -- skipping candidate"
        $failedCandidates += $c.Name
        continue
    }
    $plyArgs   += $plyPath
    $labelArgs += "--label", "$plyPath=$($c.Name)"
}

if ($failedCandidates.Count -gt 0) {
    Write-Warning "Skipped $($failedCandidates.Count) candidate(s): $($failedCandidates -join ', ')"
}
if ($plyArgs.Count -eq 0) {
    Write-Error "All candidates failed -- cannot produce matrix"
    exit 1
}

$reportPath = Join-Path $OutDir "pressure_matrix.md"
$matrixArgs = @("--matrix") + $plyArgs + $labelArgs `
            + @("-o", $reportPath, "--n-samples", $NSamples)
if ($BaselinePly -ne "") {
    if (-not (Test-Path $BaselinePly)) {
        Write-Warning "Baseline ply not found: $BaselinePly (skipping)"
    } else {
        $matrixArgs += @("--baseline", $BaselinePly)
    }
}

Write-Host "[run] check_fem_pressure --matrix ($($plyArgs.Count) candidates)"
& $PressureExe @matrixArgs
if ($LASTEXITCODE -ne 0) {
    Write-Error "check_fem_pressure failed (exit=$LASTEXITCODE)"
    exit 1
}

if (-not (Test-Path $reportPath)) {
    Write-Error "Expected report not produced: $reportPath"
    exit 1
}

Write-Host "[ok] pressure matrix written to $reportPath"

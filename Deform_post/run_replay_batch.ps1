<#
.SYNOPSIS
    Batch driver for the kidney digital-twin force-replay pipeline.

.DESCRIPTION
    For each sequence in -SeqList this driver runs, in order:
      1. run_replay.ps1 -Seq NN -OutDir <OutRoot>\seqNN
         (prep -> DeformSim exact replay -> render -> serialize)
      2. kidney_replay.py artifacts --seq-dir <dir> --mesh <mesh> --seq-id NN
         (maxu.csv + force_waveform.png + twin_sync.mp4 + montage.png + rest_vs_peak.png,
          and max|u| summary folded into replay_meta.json)
      3. unless -KeepIntermediate, delete the bulky sim\*.ply and png\*.png
         (the .pt dataset, maxu.csv, the four artifact images, labels.csv,
          forces_model.csv, camera.json, replay_meta.json, metadata.yaml are kept).

    Each sequence writes its own per-seq log + result CSV (so concurrent runs
    never interleave-corrupt a shared file); the driver merges the per-seq result
    CSVs into <OutRoot>\batch_log.csv at the end. A failing sequence records the
    error and the batch continues to the next one.

    -MaxParallel > 1 runs that many sequences concurrently via PowerShell
    background jobs (each its own process + output dir); the driver throttles the
    job pool to -MaxParallel and streams per-seq start/end progress.

.PARAMETER SeqList
    Comma list ('05,06,07') and/or inclusive ranges ('05..31'); the two forms may
    be mixed ('02,05..07,12'). Zero-padded width is preserved (05 stays "05").

.PARAMETER OutRoot
    Root output dir; each seq lands in <OutRoot>\seqNN.

.PARAMETER MaxParallel
    Max sequences to run concurrently (default 1 = strictly sequential).

.PARAMETER KeepIntermediate
    Keep sim\*.ply and png\*.png instead of deleting them after artifacts.

.NOTES
    Author/committer: WENHUIZ <84453228+zhuangwenhui@users.noreply.github.com>
#>
param(
    [Parameter(Mandatory = $true)] [string]$SeqList,
    [string]$OutRoot = 'D:\MedSim2Learn-ComplexObject\twin_full',
    [int]$MaxParallel = 1,
    [switch]$KeepIntermediate,
    [string]$MeshPath = 'D:\MedSim2Learn-ComplexObject\e1_scratch\kidney_anat.ply',
    [string]$Python = 'C:/Users/space/anaconda3/envs/MedLearning/python.exe',
    [double]$Fps = 30.0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
$RunReplay = Join-Path $ScriptDir 'run_replay.ps1'
$ReplayPy = Join-Path $ScriptDir 'kidney_replay.py'

foreach ($pair in @(@($RunReplay, 'run_replay.ps1'), @($ReplayPy, 'kidney_replay.py'),
                    @($MeshPath, 'mesh'))) {
    if (-not (Test-Path -LiteralPath $pair[0])) {
        throw ("{0} not found: {1}" -f $pair[1], $pair[0])
    }
}

# --- Parse -SeqList into an ordered, de-duplicated list of zero-padded tokens. ---
function Expand-SeqList([string]$spec) {
    $out = [System.Collections.Generic.List[string]]::new()
    $seen = [System.Collections.Generic.HashSet[string]]::new()
    foreach ($tok in ($spec -split ',')) {
        $t = $tok.Trim()
        if ($t -eq '') { continue }
        if ($t -match '^\s*(\d+)\s*\.\.\s*(\d+)\s*$') {
            $a = [int]$Matches[1]; $b = [int]$Matches[2]
            $width = [Math]::Max($Matches[1].Length, $Matches[2].Length)
            $step = if ($a -le $b) { 1 } else { -1 }
            for ($i = $a; ; $i += $step) {
                $s = ([string]$i).PadLeft($width, '0')
                if ($seen.Add($s)) { $out.Add($s) }
                if ($i -eq $b) { break }
            }
        }
        elseif ($t -match '^\d+$') {
            if ($seen.Add($t)) { $out.Add($t) }
        }
        else {
            throw "unrecognized seq token: '$t' (expected NN or NN..MM)"
        }
    }
    return $out
}

$Seqs = Expand-SeqList $SeqList
if ($Seqs.Count -eq 0) { throw "SeqList expanded to zero sequences: '$SeqList'" }

New-Item -ItemType Directory -Force -Path $OutRoot | Out-Null
$ResolvedRoot = (Resolve-Path -LiteralPath $OutRoot).Path
$LogsDir = Join-Path $ResolvedRoot '_batch_logs'
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

Write-Output "=== run_replay_batch ==="
Write-Output ("Sequences:    {0}  [{1}]" -f $Seqs.Count, ($Seqs -join ', '))
Write-Output ("OutRoot:      {0}" -f $ResolvedRoot)
Write-Output ("MaxParallel:  {0}" -f $MaxParallel)
Write-Output ("KeepInterm.:  {0}" -f [bool]$KeepIntermediate)
Write-Output ""

# --- Per-seq worker scriptblock (runs in a background job process for -MaxParallel>1). ---
# It is fully self-contained: takes absolute paths so it does not depend on the
# parent's working dir or strict-mode scope, writes its own stdout log and its
# own one-line result CSV. Any failure is caught and recorded; the worker never
# throws back into the pool so one bad seq cannot abort the batch.
$Worker = {
    param($Seq, $RunReplay, $ReplayPy, $MeshPath, $Python, $Fps,
          $ResolvedRoot, $KeepIntermediate, $LogsDir)

    $ErrorActionPreference = 'Continue'
    $OutDir = Join-Path $ResolvedRoot ("seq{0}" -f $Seq)
    $SeqLog = Join-Path $LogsDir ("seq{0}.log" -f $Seq)
    $ResCsv = Join-Path $LogsDir ("seq{0}.result.csv" -f $Seq)
    $startWall = Get-Date
    $status = 'OK'
    $errMsg = ''
    $stage = 'init'
    $frameCount = ''
    $maxuMax = ''
    $keptBytes = 0

    "[seq $Seq] START $(Get-Date -Format o)" | Out-File -FilePath $SeqLog -Encoding utf8

    try {
        # ---- Stage A: run_replay (prep -> sim -> render -> serialize) ----
        $stage = 'run_replay'
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $RunReplay `
            -Seq $Seq -OutDir $OutDir *>> $SeqLog
        if ($LASTEXITCODE -ne 0) { throw "run_replay.ps1 exit $LASTEXITCODE" }

        # ---- Stage B: artifacts ----
        $stage = 'artifacts'
        & $Python $ReplayPy artifacts --seq-dir $OutDir --mesh $MeshPath `
            --fps "$Fps" --seq-id $Seq *>> $SeqLog
        if ($LASTEXITCODE -ne 0) { throw "artifacts exit $LASTEXITCODE" }

        # ---- read frame count + maxu from replay_meta.json (survives cleanup) ----
        $meta = Get-Content -LiteralPath (Join-Path $OutDir 'replay_meta.json') -Raw | ConvertFrom-Json
        $frameCount = $meta.frame_count
        $maxuMax = $meta.maxu_max_mm

        # ---- Stage C: cleanup the bulky intermediates unless asked to keep ----
        if (-not $KeepIntermediate) {
            $stage = 'cleanup'
            $simDir = Join-Path $OutDir 'sim'
            $pngDir = Join-Path $OutDir 'png'
            if (Test-Path -LiteralPath $simDir) {
                Get-ChildItem -LiteralPath $simDir -Recurse -Filter '*.ply' -File |
                    Remove-Item -Force
            }
            if (Test-Path -LiteralPath $pngDir) {
                Get-ChildItem -LiteralPath $pngDir -Filter '*.png' -File |
                    Remove-Item -Force
            }
        }

        # ---- disk footprint kept after cleanup ----
        if (Test-Path -LiteralPath $OutDir) {
            $keptBytes = (Get-ChildItem -LiteralPath $OutDir -Recurse -File |
                Measure-Object -Property Length -Sum).Sum
            if ($null -eq $keptBytes) { $keptBytes = 0 }
        }
    }
    catch {
        $status = 'FAIL'
        $errMsg = ($_ | Out-String).Trim() -replace '[\r\n]+', ' '
        "[seq $Seq] ERROR in stage '$stage': $errMsg" | Out-File -FilePath $SeqLog -Append -Encoding utf8
    }

    $endWall = Get-Date
    $wallSec = [Math]::Round(($endWall - $startWall).TotalSeconds, 1)
    "[seq $Seq] END $(Get-Date -Format o)  status=$status wall=${wallSec}s" |
        Out-File -FilePath $SeqLog -Append -Encoding utf8

    # One-line result CSV (header + row) so the parent merge is order-agnostic.
    $keptMB = [Math]::Round($keptBytes / 1MB, 1)
    $row = [PSCustomObject]@{
        seq          = $Seq
        status       = $status
        start        = $startWall.ToString('o')
        end          = $endWall.ToString('o')
        wall_seconds = $wallSec
        frame_count  = $frameCount
        maxu_max_mm  = $maxuMax
        kept_mb      = $keptMB
        fail_stage   = if ($status -eq 'FAIL') { $stage } else { '' }
        error        = $errMsg
    }
    $row | Export-Csv -LiteralPath $ResCsv -NoTypeInformation -Encoding utf8

    # Emit a compact progress object back to the parent (visible via Receive-Job).
    [PSCustomObject]@{ seq = $Seq; status = $status; wall = $wallSec;
        frames = $frameCount; maxu = $maxuMax; keptMB = $keptMB; stage = $stage }
}

$batchStart = Get-Date
$jobs = @{}            # job -> seq
$completed = 0
$queue = [System.Collections.Queue]::new($Seqs)

# Throttled launch loop: keep up to MaxParallel jobs running.
while ($queue.Count -gt 0 -or $jobs.Count -gt 0) {
    while ($jobs.Count -lt $MaxParallel -and $queue.Count -gt 0) {
        $seq = [string]$queue.Dequeue()
        Write-Output ("[launch] seq {0}  ({1} running, {2} queued)" -f `
            $seq, ($jobs.Count + 1), $queue.Count)
        $j = Start-Job -ScriptBlock $Worker -ArgumentList `
            $seq, $RunReplay, $ReplayPy, $MeshPath, $Python, $Fps, `
            $ResolvedRoot, [bool]$KeepIntermediate, $LogsDir
        $jobs[$j.Id] = @{ Job = $j; Seq = $seq }
    }

    # Wait for at least one job to finish, then reap all finished ones.
    $running = $jobs.Values | ForEach-Object { $_.Job }
    $null = Wait-Job -Job $running -Any -Timeout 3600
    foreach ($id in @($jobs.Keys)) {
        $entry = $jobs[$id]
        if ($entry.Job.State -in @('Completed', 'Failed', 'Stopped')) {
            $res = Receive-Job -Job $entry.Job
            Remove-Job -Job $entry.Job -Force
            $jobs.Remove($id)
            $completed++
            $p = $res | Select-Object -Last 1
            if ($null -ne $p) {
                Write-Output ("[done {0}/{1}] seq {2}  status={3} wall={4}s frames={5} maxu={6}mm kept={7}MB" -f `
                    $completed, $Seqs.Count, $p.seq, $p.status, $p.wall, $p.frames, $p.maxu, $p.keptMB)
            }
            else {
                Write-Output ("[done {0}/{1}] seq {2}  (no result object; check log)" -f `
                    $completed, $Seqs.Count, $entry.Seq)
            }
        }
    }
}

# --- Merge per-seq result CSVs into batch_log.csv (in SeqList order). ---
$BatchLog = Join-Path $ResolvedRoot 'batch_log.csv'
$rows = foreach ($seq in $Seqs) {
    $rc = Join-Path $LogsDir ("seq{0}.result.csv" -f $seq)
    if (Test-Path -LiteralPath $rc) {
        Import-Csv -LiteralPath $rc
    }
    else {
        [PSCustomObject]@{ seq = $seq; status = 'NO_RESULT'; start = ''; end = '';
            wall_seconds = ''; frame_count = ''; maxu_max_mm = ''; kept_mb = '';
            fail_stage = 'no_result_csv'; error = 'worker produced no result CSV' }
    }
}
$rows | Export-Csv -LiteralPath $BatchLog -NoTypeInformation -Encoding utf8

$batchWall = [Math]::Round(((Get-Date) - $batchStart).TotalSeconds, 1)
$nOk = ($rows | Where-Object { $_.status -eq 'OK' }).Count
$nFail = $rows.Count - $nOk
Write-Output ""
Write-Output "=== batch complete ==="
Write-Output ("Total wall:   {0} s" -f $batchWall)
Write-Output ("OK / FAIL:    {0} / {1}" -f $nOk, $nFail)
Write-Output ("batch_log:    {0}" -f $BatchLog)
Write-Output ("per-seq logs: {0}" -f $LogsDir)
if ($nFail -gt 0) {
    Write-Output "FAILED sequences:"
    $rows | Where-Object { $_.status -ne 'OK' } |
        ForEach-Object { Write-Output ("  seq {0}: [{1}] {2}" -f $_.seq, $_.fail_stage, $_.error) }
}

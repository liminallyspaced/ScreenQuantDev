# SceneQuant test umbrella (review P5): every installed Blender x every suite.
# Usage:  pwsh -NoProfile -File tests/run_all.ps1 [-BlenderExe <path>] [-IncludeGolden]
#   -BlenderExe    run against one specific blender.exe instead of globbing
#                  "C:/Program Files/Blender Foundation/Blender */blender.exe" (CI use).
#   -IncludeGolden also run tests/test_golden.py — it RENDERS frames; never use
#                  it while a benchmark is running on this machine.
# Exit codes: 0 = all suites green on all Blenders; 1 = any red.
# NOTE: never pipe Blender output through Select-String/Select-Object -First —
# it kills the process mid-run. All output redirects to tests/logs/.

[CmdletBinding()]
param(
    [string]$BlenderExe,
    [switch]$IncludeGolden
)

$TestsDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $TestsDir
$LogDir = Join-Path $TestsDir 'logs'
$BadScene = Join-Path $RepoRoot 'bench/bad_scene.blend'

# Suite order: cheap fixture-building suites first, heavy bench-scene suites last.
$Suites = @(
    @{ Name = 'test_journal';    Blend = $null },
    @{ Name = 'test_regression'; Blend = $null },
    @{ Name = 'test_estimator';     Blend = $null },
    @{ Name = 'test_speed_solver';  Blend = $null },
    @{ Name = 'test_sample_knee';   Blend = $null },
    @{ Name = 'test_fit_budget';    Blend = $null },
    @{ Name = 'test_headless';   Blend = $BadScene }
)
if ($IncludeGolden) {
    $Suites += @{ Name = 'test_golden'; Blend = $BadScene }
}

if ($BlenderExe) {
    if (-not (Test-Path $BlenderExe)) {
        Write-Error "Blender executable not found: $BlenderExe"
        exit 1
    }
    $Blenders = @(Get-Item $BlenderExe)
} else {
    $Blenders = @(Get-ChildItem 'C:/Program Files/Blender Foundation/Blender */blender.exe' `
        -ErrorAction SilentlyContinue | Sort-Object FullName)
}
if ($Blenders.Count -eq 0) {
    Write-Error 'No Blender installs found; pass -BlenderExe <path to blender.exe>.'
    exit 1
}
foreach ($suite in $Suites) {
    $script = Join-Path $TestsDir "$($suite.Name).py"
    if (-not (Test-Path $script)) { Write-Error "Missing test suite: $script"; exit 1 }
}
if (-not (Test-Path $BadScene)) {
    Write-Error ("Missing $BadScene - regenerate with: blender -b --factory-startup " +
        "--python bench/make_bad_scene.py -- --out bench/bad_scene.blend")
    exit 1
}

New-Item -ItemType Directory -Force $LogDir | Out-Null
$Results = @()
foreach ($b in $Blenders) {
    $verTag = ($b.Directory.Name -replace '[^0-9.]', '')
    if (-not $verTag) { $verTag = $b.Directory.Name }
    foreach ($suite in $Suites) {
        $script = Join-Path $TestsDir "$($suite.Name).py"
        $log = Join-Path $LogDir "$verTag-$($suite.Name).log"
        $blenderArgs = @('-b', '--factory-startup')
        if ($suite.Blend) { $blenderArgs += $suite.Blend }
        $blenderArgs += @('--python-exit-code', '1', '--python', $script)
        $global:LASTEXITCODE = 1  # a launch failure must read as FAIL, not stale success
        & $b.FullName @blenderArgs *> $log
        $passed = ($LASTEXITCODE -eq 0)
        $verdict = if ($passed) { 'PASS' } else { 'FAIL' }
        $color = if ($passed) { 'Green' } else { 'Red' }
        Write-Host "$verdict  Blender $verTag  $($suite.Name)" -ForegroundColor $color
        $Results += [pscustomobject]@{
            Blender = $verTag
            Suite   = $suite.Name
            Result  = $verdict
            Log     = $log
        }
    }
}

Write-Host ''
$Results | Format-Table -AutoSize | Out-String | Write-Host
$failed = @($Results | Where-Object { $_.Result -eq 'FAIL' })
if ($failed.Count -gt 0) {
    Write-Host "$($failed.Count) suite run(s) FAILED — see logs above." -ForegroundColor Red
    exit 1
}
Write-Host "All $($Results.Count) suite runs passed." -ForegroundColor Green
exit 0

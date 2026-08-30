[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$BlenderExe,
    [Parameter(Mandatory=$true)][string]$BlendFile,
    [Parameter(Mandatory=$true)][string]$Output,
    [string]$Label = 'problem-scene',
    [int]$Repeats = 2,
    [string]$Frames = ''
)

$ErrorActionPreference = 'Stop'
$Runner = Join-Path $PSScriptRoot 'preserve_look_benchmark.py'
$BlenderPath = (Resolve-Path -LiteralPath $BlenderExe).Path
$ScenePath = (Resolve-Path -LiteralPath $BlendFile).Path
$OutputPath = [System.IO.Path]::GetFullPath($Output)
$ArgsList = @(
    '-b', $ScenePath,
    '--python-exit-code', '1',
    '--python', $Runner,
    '--', '--output', $OutputPath,
    '--label', $Label,
    '--repeats', [string][Math]::Max(1, $Repeats)
)
if ($Frames) {
    $ArgsList += @('--frames', $Frames)
}
& $BlenderPath @ArgsList
exit $LASTEXITCODE

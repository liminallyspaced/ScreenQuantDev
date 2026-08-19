# Build scenequant-<ver>.zip and publish a GitHub Release.
# Usage:  pwsh -NoProfile -File tools/ship.ps1 [-DryRun]
#
# Requires: gh logged in as liminallyspaced with `repo` scope.
# Never create a new repo. Never send a Cursor GitHub-connect card.
# See AGENTS.md.

[CmdletBinding()]
param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $RepoRoot 'scenequant'
$Manifest = Join-Path $Source 'blender_manifest.toml'
$DistDir = Join-Path $RepoRoot 'dist'
$OwnerRepo = 'liminallyspaced/ScreenQuantDev'

if (-not (Test-Path $Manifest)) { throw "Missing $Manifest" }

$manifestText = Get-Content -Raw $Manifest
if ($manifestText -notmatch '(?m)^version\s*=\s*"([^"]+)"') {
    throw "Could not read version from $Manifest"
}
$Version = $Matches[1]
$Tag = "v$Version"
$ZipName = "scenequant-$Version.zip"
$ZipPath = Join-Path $DistDir $ZipName

Write-Host "SceneQuant $Version  ->  $OwnerRepo  $Tag"

$auth = gh auth status 2>&1 | Out-String
if ($auth -notmatch 'Logged in to github.com account liminallyspaced') {
    throw "gh is not liminallyspaced. Run: gh auth switch --user liminallyspaced"
}

if ($DryRun) {
    Write-Host "Dry run — would zip $Source -> $ZipPath and gh release create $Tag"
    exit 0
}

New-Item -ItemType Directory -Force $DistDir | Out-Null
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }

$stage = Join-Path $env:TEMP "scenequant-ship-$Version"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory $stage | Out-Null
Copy-Item $Source (Join-Path $stage 'scenequant') -Recurse
Get-ChildItem $stage -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
Get-ChildItem $stage -Recurse -File -Filter '*.pyc' | Remove-Item -Force

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $stage,
    $ZipPath,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $false
)
Remove-Item $stage -Recurse -Force

$bytes = (Get-Item $ZipPath).Length
Write-Host "Zip $bytes bytes  $ZipPath"

$notes = @"
Install **$ZipName** from Assets. Do not install Source code.

itch: https://liminalvisual.itch.io/scenequant
Gumroad: https://8139959199815.gumroad.com/l/exyxdi

Measured pairs only — Classroom 41%, loft 52%, loft on Blender 5.1 62%.
"@

# Create the GitHub tag via `gh release` (--target main). Do not `git push` a
# tag here: that would also fire .github/workflows/release.yml and attach a
# second zip built on Ubuntu.
$existing = gh release view $Tag --repo $OwnerRepo 2>$null
if ($LASTEXITCODE -eq 0 -and $existing) {
    Write-Host "Release $Tag exists — uploading zip (clobber)"
    gh release upload $Tag $ZipPath --repo $OwnerRepo --clobber
} else {
    gh release create $Tag $ZipPath --repo $OwnerRepo --target main --title "SceneQuant $Version" --notes $notes
}

Write-Host "Done  https://github.com/$OwnerRepo/releases/tag/$Tag"

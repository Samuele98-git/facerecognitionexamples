# One-time model fetch for OFFLINE operation (Windows).
# Downloads + extracts the buffalo_l face model into backend/models/buffalo_l so it can be
# baked into the Docker image. Run this once on a machine with internet; afterwards the whole
# system runs air-gapped. Re-running is a no-op if the model is already present.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dir = Join-Path $root "backend\models"
$target = Join-Path $dir "buffalo_l"
$url = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"

if (Test-Path (Join-Path $target "w600k_r50.onnx")) {
    Write-Host "Model already present at $target — nothing to do."
    exit 0
}

New-Item -ItemType Directory -Force -Path $dir | Out-Null
$zip = Join-Path $dir "buffalo_l.zip"
Write-Host "Downloading face model (~275 MB) ..."
& curl.exe -L --fail --retry 5 --retry-delay 3 -o "$zip" "$url"

$tmp = Join-Path $dir "_extract"
if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
Expand-Archive -Path $zip -DestinationPath $tmp -Force
$parent = (Get-ChildItem $tmp -Recurse -Filter *.onnx | Select-Object -First 1).Directory.FullName
New-Item -ItemType Directory -Force -Path $target | Out-Null
Get-ChildItem $parent -File | Move-Item -Destination $target -Force
Remove-Item -Recurse -Force $tmp
Remove-Item $zip
Write-Host "Model ready at $target"
Get-ChildItem $target | ForEach-Object { "  {0}" -f $_.Name }

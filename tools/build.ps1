$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$destination = Join-Path $projectRoot 'dist\ManyYasuo'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
# Keep debug information: MyGo's release invocation hit a local file-access error.
# Explicit output avoids running a temporary executable during packaging.
# Resource edits do not change Go's build ID; never reuse the patched output.
$intermediate = Join-Path $projectRoot 'build\ManyYasuo-portable.exe'
if (Test-Path -LiteralPath $intermediate) { Remove-Item -LiteralPath $intermediate -Force }
& "$PSScriptRoot/go.ps1" build -ldflags '-H=windowsgui -X main.production=1' -o build/ManyYasuo-portable.exe ./cmd/manyyasuo
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& "$PSScriptRoot/go.ps1" build -o build/winresource.exe ./cmd/winresource
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $projectRoot 'build\winresource.exe') (Join-Path $projectRoot 'build\ManyYasuo-portable.exe') (Join-Path $projectRoot 'assets\app-icon.ico')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Copy-Item -LiteralPath (Join-Path $projectRoot 'build\ManyYasuo-portable.exe') -Destination (Join-Path $destination 'ManyYasuo.exe')
Write-Output "便携版：$destination\ManyYasuo.exe"

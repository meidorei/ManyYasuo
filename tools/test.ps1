$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
New-Item -ItemType Directory -Force -Path (Join-Path $projectRoot 'build\tests') | Out-Null
# Integration/performance tests are opt-in through MANYYASUO_7Z and
# MANYYASUO_PERFORMANCE. A failed junction test must not silently be skipped.
& "$PSScriptRoot/go.ps1" test -o build/tests/ ./...
exit $LASTEXITCODE

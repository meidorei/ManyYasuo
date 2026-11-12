$GoArgs = $args
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$goCommand = Get-Command go -ErrorAction SilentlyContinue
$goExecutable = if ($goCommand) { $goCommand.Source } else { 'D:\SOFTWARE\Go\1.27.4\bin\go.exe' }
if (-not (Test-Path -LiteralPath $goExecutable)) { throw '请先配置已有 Go SDK；本脚本不会自动安装。' }
# Process-local settings only. Missing dependencies fail instead of downloading.
$env:GOTOOLCHAIN = 'local'
$env:PATH = (Split-Path $goExecutable -Parent) + ';' + $env:PATH
$env:GOPROXY = 'off'
$env:GOSUMDB = 'off'
$env:GOCACHE = Join-Path $projectRoot 'build\go-cache'
$env:GOTMPDIR = Join-Path $projectRoot 'build\tmp'
$env:TEMP = $env:GOTMPDIR
$env:TMP = $env:GOTMPDIR
New-Item -ItemType Directory -Force -Path $env:GOCACHE,$env:GOTMPDIR | Out-Null
Push-Location $projectRoot
try { & $goExecutable @GoArgs; $goExitCode = $LASTEXITCODE } finally { Pop-Location }
exit $goExitCode

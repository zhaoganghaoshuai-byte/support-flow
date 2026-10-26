$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create .venv and install the project first. See README.md.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) { throw 'Build the frontend first: cd frontend; npm ci; npm run build' }
Write-Host 'SupportFlow: http://127.0.0.1:8010'
& $pythonPath -m supportflow.cli

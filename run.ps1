# Keep one launcher implementation for PowerShell and double-click startup.
& (Join-Path $PSScriptRoot 'run.bat') --no-pause @args
exit $LASTEXITCODE

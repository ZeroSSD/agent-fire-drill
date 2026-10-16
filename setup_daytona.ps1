$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python virtual environment.' }
}

& $pythonPath -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Could not install the Daytona SDK.' }

if (-not $env:DAYTONA_API_KEY) {
    $secureKey = Read-Host 'Daytona API key (hidden; kept only in this terminal session)' -AsSecureString
    $env:DAYTONA_API_KEY = [System.Net.NetworkCredential]::new('', $secureKey).Password
    $secureKey.Dispose()
    Remove-Variable secureKey
}
if (-not $env:DAYTONA_API_KEY) { throw 'A Daytona API key is required.' }

& $pythonPath sandbox_smoke.py
$smokeExitCode = $LASTEXITCODE
Write-Host "Smoke test exit code: $smokeExitCode"
if ($smokeExitCode -ne 0) { throw "Smoke test failed with exit code $smokeExitCode. Review the output above." }

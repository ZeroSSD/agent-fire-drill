# Run in the same VS Code terminal as the experiment. Credentials stay in memory.
param([switch]$Replace)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

if ($Replace -or -not $env:ARIZE_API_KEY) {
    $arizeSecret = Read-Host 'Arize API key (paste here; input is hidden)' -AsSecureString
    try {
        $env:ARIZE_API_KEY = [System.Net.NetworkCredential]::new('', $arizeSecret).Password
    }
    finally {
        $arizeSecret.Dispose()
        Remove-Variable arizeSecret
    }
}
if ($Replace -or -not $env:ARIZE_SPACE_ID) {
    $env:ARIZE_SPACE_ID = (Read-Host 'Arize Space ID (Settings > API Keys)').Trim()
}
if (-not $env:ARIZE_API_KEY -or -not $env:ARIZE_SPACE_ID) {
    throw 'Both Arize API key and Space ID are required.'
}

Write-Host 'Arize configured for this terminal. Project: agent-fire-drill'
$arizePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $arizePython)) { $arizePython = 'python' }
& $arizePython arize_smoke.py
if ($LASTEXITCODE -ne 0) { throw 'Arize setup check failed. Review the output above.' }

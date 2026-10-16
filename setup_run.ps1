# Configure only this PowerShell session. Never writes a key to a file.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
foreach ($keyName in @('DAYTONA_API_KEY', 'LLM_API_KEY', 'ARIZE_API_KEY')) {
    if (-not [Environment]::GetEnvironmentVariable($keyName, 'Process')) {
        $secretValue = Read-Host "$keyName (hidden)" -AsSecureString
        [Environment]::SetEnvironmentVariable($keyName, [System.Net.NetworkCredential]::new('', $secretValue).Password, 'Process')
        $secretValue.Dispose()
        Remove-Variable secretValue
    }
}
if (-not $env:ARIZE_SPACE_ID) { $env:ARIZE_SPACE_ID = Read-Host 'Arize Space ID' }
if (-not $env:LLM_BASE_URL) {
    $env:LLM_BASE_URL = Read-Host 'LLM base URL (Gemini: https://generativelanguage.googleapis.com/v1beta/openai)'
}
if (-not $env:LLM_MODEL) { $env:LLM_MODEL = Read-Host 'Exact model name from your working Gemini reference run' }
Write-Host 'Environment configured for this terminal. Run .\.venv\Scripts\python.exe run_experiment.py'

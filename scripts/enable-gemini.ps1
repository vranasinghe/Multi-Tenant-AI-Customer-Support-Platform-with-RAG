# Switch the local stack to Google Gemini (chat + embeddings) via its OpenAI-compatible API.
#
#   powershell -ExecutionPolicy Bypass -File scripts/enable-gemini.ps1
#
# Prompts for the key with hidden input, writes the settings into the gitignored `.env`
# (existing lines are replaced, everything else is kept) and recreates the containers.
# The key is never printed or passed on a command line.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) { throw ".env not found. Run: Copy-Item .env.example .env" }

$secure = Read-Host 'Paste your Gemini API key (input is hidden)' -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
if ([string]::IsNullOrWhiteSpace($key)) { throw 'No key entered.' }
$key = $key.Trim()

$base = 'https://generativelanguage.googleapis.com/v1beta/openai'
# Operator estimates in USD per million input/output tokens - verify against Google's pricing page.
$prices = '{"gpt-4.1-mini":[0.40,1.60],"gpt-4.1-nano":[0.10,0.40],"gpt-4.1":[2.0,8.0],' +
          '"gemini-3.5-flash":[0.30,2.50],"gemini-3.5-flash-lite":[0.10,0.40]}'

$settings = [ordered]@{
    LLM_PROVIDER        = 'openai_compatible'
    LLM_BASE_URL        = $base
    LLM_API_KEY         = $key
    EMBEDDING_PROVIDER  = 'openai_compatible'
    EMBEDDING_BASE_URL  = $base
    EMBEDDING_API_KEY   = $key
    # 1536 is the dimension of the database column (vector(1536)); gemini-embedding-001 supports it.
    EMBEDDING_MODEL     = 'gemini-embedding-001'
    CHAT_MODEL_PRICES   = $prices
}

$lines = [System.Collections.Generic.List[string]]::new()
$lines.AddRange([string[]](Get-Content -Path $envFile -Encoding UTF8))
foreach ($name in $settings.Keys) {
    $pattern = '^\s*' + [regex]::Escape($name) + '='
    $index = -1
    for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -match $pattern) { $index = $i } }
    $entry = "$name=$($settings[$name])"
    if ($index -ge 0) { $lines[$index] = $entry } else { $lines.Add($entry) }
}
[System.IO.File]::WriteAllLines($envFile, $lines, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "Updated $envFile (Gemini chat + embeddings)."

Push-Location $root
try { docker compose up -d --build --force-recreate --wait }
finally { Pop-Location }
Write-Host 'Done. In the dashboard, pick a Gemini model on step 4 (Model) of the chatbot wizard.'

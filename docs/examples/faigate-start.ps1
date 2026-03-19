$ErrorActionPreference = "Stop"

$RepoRoot = Join-Path $env:USERPROFILE "services\faigate"
$ConfigDir = Join-Path $env:APPDATA "fusionAIze Gate"
$StateDir = Join-Path $env:LOCALAPPDATA "fusionAIze Gate"
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$ConfigPath = Join-Path $ConfigDir "config.yaml"
$EnvPath = Join-Path $ConfigDir "faigate.env"
$DbPath = Join-Path $StateDir "faigate.db"

New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

if (Test-Path $EnvPath) {
    Get-Content $EnvPath | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') {
            return
        }
        $parts = $_ -split '=', 2
        if ($parts.Length -eq 2) {
            [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1])
        }
    }
}

$env:FAIGATE_DB_PATH = $DbPath

& $PythonExe -m faigate --config $ConfigPath

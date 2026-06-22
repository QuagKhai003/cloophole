# cloophole installer — run with:
#   irm https://raw.githubusercontent.com/OWNER/REPO/main/install.ps1 | iex
#
# Downloads the standalone cloophole.exe (no Python/pip needed) into
# %LOCALAPPDATA%\Programs\cloophole and adds it to your user PATH.
# Then just:  cloophole open

$ErrorActionPreference = "Stop"

# --- which repo to pull the release from ------------------------------------
# Override by setting $env:CLOOPHOLE_OWNER / $env:CLOOPHOLE_REPO before running.
$Owner = if ($env:CLOOPHOLE_OWNER) { $env:CLOOPHOLE_OWNER } else { "OWNER" }
$Repo  = if ($env:CLOOPHOLE_REPO)  { $env:CLOOPHOLE_REPO }  else { "cloophole" }

$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\cloophole"
$ExePath    = Join-Path $InstallDir "cloophole.exe"
$Url        = "https://github.com/$Owner/$Repo/releases/latest/download/cloophole.exe"

Write-Host "cloophole installer" -ForegroundColor Cyan
Write-Host "  source : $Url"
Write-Host "  target : $ExePath"

# --- stop a running instance so we can overwrite the exe --------------------
if (Test-Path $ExePath) {
    try { & $ExePath close 2>$null | Out-Null } catch {}
    Start-Sleep -Milliseconds 500
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

Write-Host "downloading..." -ForegroundColor Cyan
Invoke-WebRequest -Uri $Url -OutFile $ExePath -UseBasicParsing

# --- add to user PATH (idempotent) -----------------------------------------
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$InstallDir*") {
    $newPath = if ($userPath) { "$userPath;$InstallDir" } else { $InstallDir }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    $env:Path = "$env:Path;$InstallDir"   # available in THIS session immediately
    Write-Host "added to PATH." -ForegroundColor Green
}

Write-Host ""
Write-Host "installed." -ForegroundColor Green
Write-Host "Run:  " -NoNewline; Write-Host "cloophole open" -ForegroundColor Yellow
Write-Host "(if 'cloophole' isn't found, open a new terminal first.)"

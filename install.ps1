# cloophole installer — run with:
#   irm https://raw.githubusercontent.com/QuagKhai003/cloophole/main/install.ps1 | iex
#
# Downloads the standalone cloophole.exe (no Python/pip needed) into
# %LOCALAPPDATA%\Programs\cloophole and adds it to your user PATH.
# It KILLS any running cloophole first (so the exe can be replaced and no old
# build keeps running), downloads with retries, and verifies the build.
# Then just:  cloophole open

$ErrorActionPreference = "Stop"

$Owner = if ($env:CLOOPHOLE_OWNER) { $env:CLOOPHOLE_OWNER } else { "QuagKhai003" }
$Repo  = if ($env:CLOOPHOLE_REPO)  { $env:CLOOPHOLE_REPO }  else { "cloophole" }

$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\cloophole"
$ExePath    = Join-Path $InstallDir "cloophole.exe"
$Url        = "https://github.com/$Owner/$Repo/releases/latest/download/cloophole.exe"

Write-Host "cloophole installer" -ForegroundColor Cyan
Write-Host "  source : $Url"
Write-Host "  target : $ExePath"

# --- stop EVERY running cloophole so the exe is unlocked and no old build lingers
# (the exe AND any python/vbs daemon left by older builds), but never this shell
Write-Host "stopping any running cloophole..." -ForegroundColor Yellow
Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $PID -and
    $_.Name -in @('cloophole.exe', 'python.exe', 'pythonw.exe', 'wscript.exe', 'cscript.exe') -and
    $_.CommandLine -like '*cloophole*'
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
for ($i = 0; $i -lt 20; $i++) {
    if (-not (Get-Process cloophole -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 300
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# Resolve the FRESH asset URL via the API. The .../releases/latest/download/ alias
# is served through a CDN that caches the OLD binary, so we ask the API for the
# current asset's browser_download_url (its id changes each upload -> not cached).
try {
    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$Owner/$Repo/releases/tags/latest" `
        -Headers @{ "User-Agent" = "cloophole-installer" }
    $asset = $rel.assets | Where-Object { $_.name -eq "cloophole.exe" } | Select-Object -First 1
    if ($asset) { $Url = $asset.browser_download_url; Write-Host "  asset  : $Url" }
} catch { Write-Host "  (couldn't query API; using the latest alias)" -ForegroundColor Yellow }

# --- download with retries (curl.exe is reliable on connection drops) ---------
Write-Host "downloading..." -ForegroundColor Cyan
$curl = Join-Path $env:SystemRoot "System32\curl.exe"
if (Test-Path $curl) {
    & $curl -L --fail --retry 5 --retry-all-errors --connect-timeout 20 -o $ExePath $Url
    if ($LASTEXITCODE -ne 0) { throw "download failed (curl exit $LASTEXITCODE)" }
} else {
    $ok = $false
    for ($i = 1; $i -le 5; $i++) {
        try { Invoke-WebRequest -Uri $Url -OutFile $ExePath -UseBasicParsing; $ok = $true; break }
        catch { Write-Host "  retry $i/5..." -ForegroundColor Yellow; Start-Sleep -Seconds 2 }
    }
    if (-not $ok) { throw "download failed after 5 attempts" }
}

if (-not (Test-Path $ExePath) -or (Get-Item $ExePath).Length -lt 1MB) {
    throw "downloaded file looks incomplete — try again"
}

# --- add to user PATH (idempotent) -----------------------------------------
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$InstallDir*") {
    $newPath = if ($userPath) { "$userPath;$InstallDir" } else { $InstallDir }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    $env:Path = "$env:Path;$InstallDir"
    Write-Host "added to PATH." -ForegroundColor Green
}

# --- verify which build we just installed -----------------------------------
$ver = ""
try { $ver = (& $ExePath version 2>$null | Out-String).Trim() } catch {}

Write-Host ""
Write-Host "installed. $ver" -ForegroundColor Green

# --- launch it: fresh install OR update both end with the app running ----------
Write-Host "opening cloophole..." -ForegroundColor Cyan
try { & $ExePath open | Out-Null } catch {}

Write-Host ""
Write-Host "Done. The cloophole window is open and watching." -ForegroundColor Green
Write-Host "Restart Claude Code once so it loads the zero-quota limit hook."
Write-Host "(CLI also available as 'cloophole' in a new terminal.)"

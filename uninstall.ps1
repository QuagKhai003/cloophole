# cloophole uninstaller — run with:
#   irm https://raw.githubusercontent.com/OWNER/REPO/main/uninstall.ps1 | iex
#
# Stops the app, removes the exe + PATH entry + app data.

$ErrorActionPreference = "SilentlyContinue"

$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\cloophole"
$ExePath    = Join-Path $InstallDir "cloophole.exe"
$DataDir    = Join-Path $env:USERPROFILE ".cloophole"

Write-Host "cloophole uninstaller" -ForegroundColor Cyan

if (Test-Path $ExePath) {
    try { & $ExePath close | Out-Null } catch {}
    Start-Sleep -Milliseconds 500
}

# remove PATH entry
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -like "*$InstallDir*") {
    $parts = $userPath.Split(';') | Where-Object { $_ -and $_ -ne $InstallDir }
    [Environment]::SetEnvironmentVariable("Path", ($parts -join ';'), "User")
    Write-Host "removed from PATH." -ForegroundColor Green
}

Remove-Item -Recurse -Force $InstallDir
Remove-Item -Recurse -Force $DataDir
Write-Host "removed app + data." -ForegroundColor Green

# cloophole uninstaller — run with:
#   irm https://raw.githubusercontent.com/QuagKhai003/cloophole/main/uninstall.ps1 | iex
#
# Stops EVERYTHING, removes the Claude hook, then deletes the exe + PATH + app data.

$ErrorActionPreference = "SilentlyContinue"

$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\cloophole"
$ExePath    = Join-Path $InstallDir "cloophole.exe"
$DataDir    = Join-Path $env:LOCALAPPDATA "cloophole"          # new home
$OldDataDir = Join-Path $env:USERPROFILE ".cloophole"          # legacy home

Write-Host "cloophole uninstaller" -ForegroundColor Cyan

if (Test-Path $ExePath) {
    # remove the rate-limit hook from Claude settings + stop watcher/window
    try { & $ExePath hook off | Out-Null } catch {}
    try { & $ExePath close   | Out-Null } catch {}
    Start-Sleep -Milliseconds 400
}

# Hard sweep: kill any leftover/hanging cloophole process by name (the complaint
# was orphaned processes surviving uninstall). This shell is not cloophole, so it
# can kill them all safely.
$procs = Get-Process cloophole -ErrorAction SilentlyContinue
if ($procs) {
    $procs | Stop-Process -Force
    Write-Host "stopped $($procs.Count) running cloophole process(es)." -ForegroundColor Green
    Start-Sleep -Milliseconds 300
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
Remove-Item -Recurse -Force $OldDataDir
if (Test-Path $InstallDir) {
    Write-Host "note: $InstallDir is still locked; close any cloophole window and re-run." -ForegroundColor Yellow
} else {
    Write-Host "removed app + data." -ForegroundColor Green
}
Write-Host "done. Open a NEW terminal (this one still has the old PATH)." -ForegroundColor Cyan

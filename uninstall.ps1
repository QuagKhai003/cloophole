# cloophole uninstaller — run with:
#   irm https://raw.githubusercontent.com/QuagKhai003/cloophole/main/uninstall.ps1 | iex
#
# Completely removes cloophole: the rate-limit hook, EVERY running process
# (exe + python + vbs), any legacy autostart, the PATH entry, the exe, and all
# app data (both the new %LOCALAPPDATA%\cloophole and the legacy ~/.cloophole).

$ErrorActionPreference = "SilentlyContinue"

$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\cloophole"
$ExePath    = Join-Path $InstallDir "cloophole.exe"
$DataDir    = Join-Path $env:LOCALAPPDATA "cloophole"
$OldDataDir = Join-Path $env:USERPROFILE ".cloophole"

Write-Host "cloophole uninstaller" -ForegroundColor Cyan

# 1) remove the Claude hook while the exe still exists
if (Test-Path $ExePath) {
    try { & $ExePath hook off | Out-Null } catch {}
    Start-Sleep -Milliseconds 300
}

# 1b) strip our statusLine from EVERY WSL distro's Claude settings, DIRECTLY (no
# dependence on the exe still existing). Edits ~/.claude/settings.json via the \\wsl$
# path, keeping the user's other settings.
try {
    $distros = @()
    try {
        $distros = (wsl.exe -l -q 2>$null) | ForEach-Object { ($_ -replace "`0", "").Trim() } |
            Where-Object { $_ }
    } catch {}
    if (-not $distros) { $distros = @("") }   # "" = default distro
    foreach ($d in $distros) {
        try {
            if ($d) { $sp = wsl.exe -d $d sh -c 'wslpath -w "$HOME/.claude/settings.json" 2>/dev/null' }
            else    { $sp = wsl.exe       sh -c 'wslpath -w "$HOME/.claude/settings.json" 2>/dev/null' }
            $sp = ($sp | Out-String).Trim()
            if ($sp -and (Test-Path $sp)) {
                $j = Get-Content $sp -Raw | ConvertFrom-Json
                if ($j.statusLine -and ("$($j.statusLine.command)" -like '*statusline*')) {
                    $j.PSObject.Properties.Remove('statusLine')
                    [IO.File]::WriteAllText($sp, ($j | ConvertTo-Json -Depth 30))
                    $label = if ($d) { $d } else { 'default' }
                    Write-Host "removed WSL statusLine ($label)" -ForegroundColor Green
                }
            }
        } catch {}
    }
} catch {}

# 2) kill EVERY cloophole runner (exe + python + pythonw + vbs host), not this shell
Write-Host "stopping every cloophole process..." -ForegroundColor Yellow
$runners = Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $PID -and
    $_.Name -in @('cloophole.exe', 'python.exe', 'pythonw.exe', 'wscript.exe', 'cscript.exe') -and
    $_.CommandLine -like '*cloophole*'
}
$runners | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Milliseconds 500

# 3) remove any legacy autostart (Startup shim + scheduled task)
$startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
Get-ChildItem $startup | Where-Object { $_.Name -match "cloop" } |
    ForEach-Object { Write-Host "removed $($_.FullName)" -ForegroundColor Green; Remove-Item $_.FullName }
Get-ScheduledTask | Where-Object { $_.TaskName -match "cloop" } |
    ForEach-Object { Write-Host "removed task $($_.TaskName)" -ForegroundColor Green; Unregister-ScheduledTask -TaskName $_.TaskName -Confirm:$false }

# 4) remove the PATH entry
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -like "*$InstallDir*") {
    $parts = $userPath.Split(';') | Where-Object { $_ -and $_ -ne $InstallDir }
    [Environment]::SetEnvironmentVariable("Path", ($parts -join ';'), "User")
    Write-Host "removed from PATH." -ForegroundColor Green
}

# 5) delete the exe + ALL app data (new + legacy)
foreach ($d in @($InstallDir, $DataDir, $OldDataDir)) {
    Remove-Item -Recurse -Force $d
    if (Test-Path $d) { Write-Host "note: $d still locked; close any cloophole window and re-run." -ForegroundColor Yellow }
    else { Write-Host "removed $d" -ForegroundColor Green }
}

Write-Host ""
Write-Host "cloophole fully removed. Open a NEW terminal (this one still has the old PATH)." -ForegroundColor Cyan

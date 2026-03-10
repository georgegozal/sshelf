# RemminaMac uninstaller -- Windows (PowerShell)
# Usage: powershell -ExecutionPolicy Bypass -File uninstall.ps1
#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$INSTALL_DIR = "$env:LOCALAPPDATA\remminamac"

function Info { param($msg) Write-Host "[remminamac] $msg" -ForegroundColor Green }
function Warn { param($msg) Write-Host "[remminamac] $msg" -ForegroundColor Yellow }
function Err  { param($msg) Write-Host "[remminamac] ERROR: $msg" -ForegroundColor Red; exit 1 }

if (-not (Test-Path $INSTALL_DIR)) {
    Err "RemminaMac does not appear to be installed (expected $INSTALL_DIR)."
}

$confirm = Read-Host "Remove RemminaMac from $INSTALL_DIR? [y/N]"
if ($confirm -notmatch '^[Yy]') { Write-Host "Aborted."; exit 0 }

Remove-Item -Recurse -Force $INSTALL_DIR
Info "Removed $INSTALL_DIR"

# -- Remove from user PATH if present -----------------------------------------
$userPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
$cleaned  = ($userPath -split ";") | Where-Object { $_ -ne $INSTALL_DIR } | Join-String -Separator ";"
if ($cleaned -ne $userPath) {
    [System.Environment]::SetEnvironmentVariable("PATH", $cleaned, "User")
    Info "Removed $INSTALL_DIR from user PATH."
}

# -- Note about stored data ---------------------------------------------------
Warn "Your connection database and preferences are kept at:"
Warn "  $env:APPDATA\RemminaMac\"
Warn "Delete that directory manually if you want to remove all saved connections."

Write-Host ""
Info "RemminaMac uninstalled."

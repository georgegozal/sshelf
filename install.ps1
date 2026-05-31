# sshelf installer -- Windows (PowerShell)
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1
#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$REPO_URL   = "https://github.com/georgegozal/sshelf.git"

# -- Detect if running from inside an already-cloned repo ---------------------
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
if ((Test-Path "$SCRIPT_DIR\main.py") -and (Test-Path "$SCRIPT_DIR\requirements.txt")) {
    $INSTALL_DIR = $SCRIPT_DIR
    $IN_REPO     = $true
} else {
    $INSTALL_DIR = "$env:LOCALAPPDATA\sshelf"
    $IN_REPO     = $false
}

$BIN_DIR  = $INSTALL_DIR
$LAUNCHER = "$INSTALL_DIR\sshelf.bat"

function Info  { param($msg) Write-Host "[sshelf] $msg" -ForegroundColor Green }
function Warn  { param($msg) Write-Host "[sshelf] $msg" -ForegroundColor Yellow }
function Err   { param($msg) Write-Host "[sshelf] ERROR: $msg" -ForegroundColor Red; exit 1 }

Info "Installing sshelf on Windows..."

# -- Python check -------------------------------------------------------------
$PYTHON = $null
foreach ($py in @("python", "python3", "py")) {
    try {
        $ver = & $py -c "import sys; print(sys.version_info >= (3,10))" 2>$null
        if ($ver -eq "True") { $PYTHON = $py; break }
    } catch { }
}
if (-not $PYTHON) { Err "Python 3.10+ is required. Install from https://python.org and re-run." }
Info "Using $(& $PYTHON --version)"

# -- Git check (only needed when cloning) -------------------------------------
if (-not $IN_REPO -and -not (Get-Command git -ErrorAction SilentlyContinue)) {
    Err "git is required. Install from https://git-scm.com and re-run."
}

# -- Clone or update (skipped when running from inside the repo) --------------
if ($IN_REPO) {
    Info "Running from existing repo at $INSTALL_DIR -- skipping clone."
} elseif (Test-Path "$INSTALL_DIR\.git") {
    Info "Updating existing installation..."
    git -C $INSTALL_DIR pull --ff-only
} else {
    Info "Cloning sshelf to $INSTALL_DIR..."
    git clone --depth=1 $REPO_URL $INSTALL_DIR
}

# -- Python virtual environment -----------------------------------------------
$VENV = "$INSTALL_DIR\.venv"
if (-not (Test-Path $VENV)) {
    Info "Creating virtual environment..."
    & $PYTHON -m venv $VENV
}

Info "Installing Python dependencies..."
& "$VENV\Scripts\pip.exe" install --quiet --upgrade pip
& "$VENV\Scripts\pip.exe" install --quiet -r "$INSTALL_DIR\requirements.txt"

# -- secretstorage is not needed on Windows (keyring uses Credential Manager) -

# -- Batch launcher -----------------------------------------------------------
@"
@echo off
"$VENV\Scripts\python.exe" "$INSTALL_DIR\main.py" %*
"@ | Set-Content -Encoding ASCII $LAUNCHER

Info "Launcher created: $LAUNCHER"

# -- Add to user PATH (if not already there) ----------------------------------
$userPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*$BIN_DIR*") {
    $yn = Read-Host "`n$BIN_DIR is not in your PATH. Add it? [Y/n]"
    if ($yn -notmatch '^[Nn]') {
        [System.Environment]::SetEnvironmentVariable(
            "PATH", "$userPath;$BIN_DIR", "User"
        )
        $env:PATH += ";$BIN_DIR"
        Info "Added $BIN_DIR to user PATH."
        Warn "Restart your terminal for the PATH change to take effect."
    } else {
        Warn "Skipped. Add this to your PATH manually to run 'sshelf' from anywhere:"
        Warn "  $BIN_DIR"
    }
} else {
    Info "PATH already contains $BIN_DIR."
}

# -- Done ---------------------------------------------------------------------
Write-Host ""
Info "sshelf installed successfully!"
Info "Run it with:  sshelf"
Info "(Restart your terminal if 'sshelf' is not found yet)"

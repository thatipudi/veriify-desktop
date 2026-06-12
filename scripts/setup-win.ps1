<#
  Veriify Desktop - Windows dev/build environment setup
  Installs Node + Python dependencies and builds the FastAPI backend binary.
  Run from the project root in PowerShell:
      powershell -ExecutionPolicy Bypass -File scripts\setup-win.ps1
#>

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Write-Step($msg) { Write-Host "> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  [ok] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [!] $msg" -ForegroundColor Yellow }

Write-Step "Veriify Desktop setup (Windows)"

# 1. Prerequisites
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  Write-Warn "Node.js 18+ is required - https://nodejs.org"; exit 1
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Warn "Python 3.11+ is required - https://python.org"; exit 1
}
Write-Ok ("node " + (node -v) + "   " + (python --version))

# 2. Electron + electron-builder
Write-Step "Installing Node dependencies (electron, electron-builder)..."
npm install
Write-Ok "Node dependencies installed"

# 3. Python backend dependencies + PyInstaller
Write-Step "Installing Python backend dependencies..."
python -m pip install --upgrade pip | Out-Null
python -m pip install -r backend/requirements.txt
python -m pip install pyinstaller
Write-Ok "Python dependencies + PyInstaller installed"

# 4. Build the backend into a single binary
Write-Step "Building FastAPI backend binary (PyInstaller)..."
Push-Location backend
pyinstaller --onefile --name app `
  --add-data "static;static" `
  --add-data "prompts;prompts" `
  --add-data "utils;utils" `
  app.py
Pop-Location
Write-Ok "Backend binary -> backend\dist\app.exe"

Write-Step "Done."
Write-Host "Next:"
Write-Host "  - Dev run:   npm start          (uses python backend, needs Ollama running)"
Write-Host "  - Package:   npm run build:win  (produces dist\Veriify-Setup-*.exe)"
Write-Host ""
Write-Warn "Reminder: convert assets\icon.svg -> icon.ico before packaging (see README-BUILD.md)."

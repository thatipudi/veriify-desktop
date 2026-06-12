#!/usr/bin/env bash
#
# Veriify Desktop — macOS dev/build environment setup
# Installs Node + Python dependencies and builds the FastAPI backend binary.
# Run from the project root:  bash scripts/setup-mac.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

bold() { printf "\033[1m%s\033[0m\n" "$1"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; }

bold "▶ Veriify Desktop setup (macOS)"

# 1. Prerequisites
command -v node    >/dev/null 2>&1 || { warn "Node.js 18+ is required — https://nodejs.org"; exit 1; }
command -v python3 >/dev/null 2>&1 || { warn "Python 3.11+ is required — https://python.org"; exit 1; }
ok "node $(node -v)   python $(python3 --version | awk '{print $2}')"

# 2. Electron + electron-builder
bold "▶ Installing Node dependencies (electron, electron-builder)…"
npm install
ok "Node dependencies installed"

# 3. Python backend dependencies + PyInstaller
bold "▶ Installing Python backend dependencies…"
python3 -m pip install --upgrade pip >/dev/null
python3 -m pip install -r backend/requirements.txt
python3 -m pip install pyinstaller
ok "Python dependencies + PyInstaller installed"

# 4. Build the backend into a single binary
bold "▶ Building FastAPI backend binary (PyInstaller)…"
(
  cd backend
  pyinstaller --onefile --name app \
    --add-data "static:static" \
    --add-data "prompts:prompts" \
    --add-data "utils:utils" \
    app.py
)
ok "Backend binary → backend/dist/app"

bold "▶ Done."
echo "Next:"
echo "  • Dev run:   npm start          (uses python3 backend, needs Ollama running)"
echo "  • Package:   npm run build:mac  (produces dist/Veriify-*.dmg)"
echo
warn "Reminder: convert assets/icon.svg → icon.icns before packaging (see README-BUILD.md)."

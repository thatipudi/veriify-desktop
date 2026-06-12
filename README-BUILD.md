# Building Veriify Desktop App

Veriify is a FastAPI + Ollama interview coach wrapped as a native desktop app
with **Electron** (shell + first-launch installer) and **PyInstaller** (the
Python backend compiled to a single binary).

```
veriify-desktop/
├── electron/         # Electron main process, preload, first-launch setup wizard
│   ├── main.js
│   ├── preload.js
│   ├── setup.html
│   └── package.json
├── backend/          # The FastAPI app (copy of interview-coach/)
├── assets/           # App icon (svg/png; add icns/ico before packaging)
├── scripts/          # One-shot dev/build env setup
│   ├── setup-mac.sh
│   └── setup-win.ps1
├── package.json      # Root: electron-builder config + npm scripts
└── README-BUILD.md
```

## Prerequisites
- Node.js 18+ installed
- Python 3.11+ installed
- PyInstaller: `pip install pyinstaller`
- For Mac builds: Xcode Command Line Tools (`xcode-select --install`)
- For Windows builds: run on a Windows machine

> **Quick start:** `bash scripts/setup-mac.sh` (macOS) or
> `powershell -ExecutionPolicy Bypass -File scripts\setup-win.ps1` (Windows)
> installs every dependency and builds the backend binary for you.

---

## App Icons (do this once, before packaging)

`electron-builder` needs platform icon files. Convert the provided
`assets/icon.svg`:

- **macOS:** convert `icon.svg` → `icon.icns` using
  <https://cloudconvert.com/svg-to-icns> and save it as `assets/icon.icns`
- **Windows:** convert `icon.svg` → `icon.ico` using
  <https://cloudconvert.com/svg-to-ico> and save it as `assets/icon.ico`

`assets/icon.png` (the in-app window icon) is already generated from the SVG.

> **⚠️ Windows icon required (CI + local builds).** `assets/icon.ico` is **not**
> checked into the repo. Before the Windows job in
> `.github/workflows/build.yml` (or a local `npm run build:win`) can produce the
> NSIS installer, create it:
>
> 1. Convert `assets/icon.svg` → `icon.ico` at
>    <https://cloudconvert.com/svg-to-ico>
> 2. Download the result and place it at `veriify-desktop/assets/icon.ico`
>
> The `win.icon`, `nsis.installerIcon`, and `nsis.uninstallerIcon` settings in
> `package.json` all point at this file.

---

## Mac Build

```bash
# Install dependencies
npm install

# Build Python backend into a binary
cd backend
pyinstaller --onefile --name app \
  --add-data "static:static" \
  --add-data "prompts:prompts" \
  --add-data "utils:utils" \
  app.py
cd ..

# Build Mac .dmg
npx electron-builder --mac

# Output: dist/Veriify-1.0.0-beta-arm64.dmg
```

Or simply: `npm run build:mac` (runs the backend build + electron-builder).

---

## Windows Build (run on Windows)

```bat
npm install
cd backend
pyinstaller --onefile --name app.exe ^
  --add-data "static;static" ^
  --add-data "prompts;prompts" ^
  --add-data "utils;utils" ^
  app.py
cd ..
npx electron-builder --win

REM Output: dist/Veriify-Setup-1.0.0-beta.exe
```

Or simply: `npm run build:win`.

---

## Run in development (no packaging)

```bash
npm install
npm start
```

In dev mode Electron launches the backend with `python3 backend/app.py` (so your
local Python env must have `backend/requirements.txt` installed). On first launch
the setup wizard appears; afterwards it loads the app at `http://localhost:8000`.

---

## How it runs (architecture)

1. **Ollama** — the local LLM engine. Electron starts `ollama serve` and the
   backend talks to it at `http://localhost:11434`. On first launch the setup
   wizard checks for Ollama and pulls the `llama3.1:8b` model (~5 GB).
2. **FastAPI backend** — compiled by PyInstaller to `backend/dist/app`
   (`app.exe` on Windows) and bundled via `extraResources`. Electron spawns it
   with `PORT=8000`; it serves the Veriify UI and the interview/TTS APIs.
3. **Electron shell** — loads `http://localhost:8000` once the backend is up,
   and runs the first-launch `setup.html` wizard when needed.

The backend's `app.py` is packaging-aware: when frozen it `chdir`s to
PyInstaller's `sys._MEIPASS` so the bundled `static/`, `prompts/`, and `utils/`
resolve, reads `PORT` from the environment, and binds `127.0.0.1`.

---

## Voice (Kokoro TTS) models — optional

The Kokoro neural voice needs two model files in `backend/models/`
(`kokoro-v1.0.onnx` ≈ 310 MB, `voices-v1.0.bin` ≈ 27 MB). They are **not**
bundled by default (they would bloat the binary). The app still works without
them — it falls back to the system voice (macOS `say`) and the browser voice.

To ship the neural voice offline, add the models to the PyInstaller build:

```bash
# inside backend/, append to the pyinstaller command:
  --add-data "models:models"     # macOS/Linux  (use models;models on Windows)
```

---

## Troubleshooting the backend build (heavy ML deps)

`backend/requirements.txt` pulls in native libraries (`onnxruntime` via
`kokoro-onnx`, `ctranslate2` via `faster-whisper`, `PyMuPDF`, etc.). PyInstaller
sometimes misses their data files or hidden imports. If the packaged backend
fails to start (or the window stays blank), rebuild with explicit collection:

```bash
cd backend
pyinstaller --onefile --name app \
  --add-data "static:static" \
  --add-data "prompts:prompts" \
  --add-data "utils:utils" \
  --collect-all onnxruntime \
  --collect-all kokoro_onnx \
  --collect-all faster_whisper \
  --collect-all ctranslate2 \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.protocols.websockets.websockets_impl \
  app.py
```

(On Windows swap the `:` in `--add-data` for `;`.) To verify the binary on its
own before packaging: `PORT=8000 ./backend/dist/app` then open
`http://localhost:8000`. The features degrade gracefully — if a voice/transcribe
dependency is missing, the app still runs with browser-based fallbacks.

## Distribute

Upload the `.dmg` and `.exe` from `dist/` to:
- GitHub Releases (free)
- Google Drive
- Your own website

> **Note:** unsigned builds will show Gatekeeper (macOS) / SmartScreen (Windows)
> warnings. For public distribution, code-sign and notarize the macOS build and
> sign the Windows installer.

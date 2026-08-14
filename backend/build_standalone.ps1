# Builds the standalone backend sidecar Tauri launches instead of the user
# running uvicorn by hand. Run from the `backend` directory with the venv
# available. Output lands at
# src-tauri/binaries/short-maker-backend-<target-triple>.exe -- rename the
# suffix to match your Rust host triple if it isn't x86_64-pc-windows-msvc
# (check with `rustc -vV`).

$ErrorActionPreference = "Stop"

& ".venv/Scripts/python.exe" -m PyInstaller `
  --name short-maker-backend `
  --onefile `
  --noconfirm `
  --add-data "app/pipeline/common/models/face_detection_yunet_2023mar.onnx;app/pipeline/common/models" `
  --collect-all cv2 `
  --collect-all faster_whisper `
  --collect-all ctranslate2 `
  --collect-all tokenizers `
  --collect-all google.genai `
  --exclude-module google.genai.tests `
  --exclude-module matplotlib `
  --exclude-module tkinter `
  --hidden-import app.api.projects `
  --hidden-import app.api.clips `
  --hidden-import app.api.jobs `
  --hidden-import app.api.ai_providers `
  --hidden-import app.api.subtitles `
  --hidden-import app.api.social_kit `
  --hidden-import app.api.system `
  run_server.py

$triple = (rustc -vV | Select-String "^host:").ToString().Split(" ")[1]
New-Item -ItemType Directory -Force -Path "../src-tauri/binaries" | Out-Null
Copy-Item "dist/short-maker-backend.exe" "../src-tauri/binaries/short-maker-backend-$triple.exe" -Force

Write-Host "Sidecar built: src-tauri/binaries/short-maker-backend-$triple.exe"

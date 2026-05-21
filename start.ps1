# AutoPaper — startup script
# Builds the frontend, then starts the backend (which also serves the UI).
#
# Usage:
#   .\start.ps1          → production  (backend at :8000, serves built UI)
#   .\start.ps1 -Dev     → dev mode    (Vite at :5173, API at :8000)

param([switch]$Dev)

$Root     = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Backend  = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

# ── 1. Backend dependencies ────────────────────────────────────────────────
Write-Host "`n==> Installing backend dependencies..." -ForegroundColor Cyan
pip install -r "$Backend\requirements.txt" -q
if ($LASTEXITCODE -ne 0) { Write-Host "pip install failed" -ForegroundColor Red; exit 1 }

# ── 2. Frontend dependencies ───────────────────────────────────────────────
Write-Host "==> Installing frontend dependencies..." -ForegroundColor Cyan
Push-Location $Frontend
npm install --silent
if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Host "npm install failed" -ForegroundColor Red; exit 1 }

if ($Dev) {
    # Dev: hot-reload Vite in a separate window
    Write-Host "==> Starting Vite dev server on :5173..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$Frontend'; npm run dev"
    Pop-Location
} else {
    # Production: build once, backend serves dist/
    Write-Host "==> Building frontend..." -ForegroundColor Cyan
    npm run build
    if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Host "npm build failed" -ForegroundColor Red; exit 1 }
    Pop-Location
    Write-Host "    Built to: $Frontend\dist" -ForegroundColor Green
}

# ── 3. Start backend ───────────────────────────────────────────────────────
Write-Host ""
if ($Dev) {
    Write-Host "==> AutoPaper API   → http://localhost:8000" -ForegroundColor Cyan
    Write-Host "    Frontend (dev)  → http://localhost:5173" -ForegroundColor Green
} else {
    Write-Host "==> AutoPaper ready → http://localhost:8000" -ForegroundColor Green
}
Write-Host "    Press Ctrl+C to stop.`n"

Push-Location $Backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
Pop-Location

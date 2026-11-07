# 开发形态：FastAPI(8000, --reload) + Vite(5173, 代理 /api)，浏览器只访问 5173
# 用法： .\scripts\dev.ps1 -Provider fixture
param(
    [ValidateSet("searxng", "fixture")]
    [string]$Provider = "searxng"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

# 子进程继承环境变量，避免在参数里做转义
$env:SEARCH_PROVIDER = $Provider
$env:VITE_API_TARGET = "http://127.0.0.1:8000"

$api = Start-Process -PassThru -WindowStyle Hidden powershell -ArgumentList @(
    "-NoProfile", "-Command",
    "Set-Location '$root\apps\api'; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
)

try {
    Write-Host "[api] http://127.0.0.1:8000  (provider=$Provider)" -ForegroundColor Green
    Write-Host "[web] http://127.0.0.1:5173" -ForegroundColor Green
    npm --prefix "$root\apps\web" run dev
}
finally {
    if (-not $api.HasExited) { Stop-Process -Id $api.Id -Force }
}

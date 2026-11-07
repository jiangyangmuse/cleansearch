# 发布形态：构建前端 -> FastAPI 单进程同源托管 API + 静态页
# 用法： .\scripts\serve.ps1                  （searxng）
#        .\scripts\serve.ps1 -Provider fixture （无需 Docker，固定样本三态）
param(
    [ValidateSet("searxng", "fixture")]
    [string]$Provider = "searxng",
    [int]$Port = 8000,
    [switch]$SkipBuild,
    [string]$OllamaModel
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $SkipBuild) {
    Write-Host "[build] apps/web -> dist" -ForegroundColor Cyan
    npm --prefix apps/web run build
    if ($LASTEXITCODE -ne 0) { throw "前端构建失败" }
}

# 读 .env（不覆盖已存在的环境变量）；之后 -Provider 参数优先
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | Where-Object { $_ -match '^\s*[^#][^=]*=' } | ForEach-Object {
        $pair = $_ -split "=", 2
        $key = $pair[0].Trim()
        $value = $pair[1].Trim()
        if ($key -and $value -and -not (Test-Path "Env:$key")) { Set-Item "Env:$key" $value }
    }
    Write-Host "[env] 已加载 .env" -ForegroundColor Cyan
}

$env:SEARCH_PROVIDER = $Provider
$env:API_PORT = "$Port"
if ($OllamaModel) {
    $env:LLM_PROVIDER = "openai"
    $env:LLM_BASE_URL = "http://127.0.0.1:11434/v1"
    $env:LLM_API_KEY = "ollama"
    $env:LLM_MODEL = $OllamaModel
    if (-not $env:LLM_REASONING_EFFORT) { $env:LLM_REASONING_EFFORT = "none" }
    Write-Host "[llm] 本机 Ollama: $OllamaModel" -ForegroundColor Cyan
}
if ($Provider -eq "fixture") {
    Write-Host "[mode] 固定样本：test=有结果，__empty xxx=零结果，__fail xxx=上游不可用" -ForegroundColor Yellow
}

Write-Host "[serve] http://127.0.0.1:$Port" -ForegroundColor Green
Set-Location "$root\apps\api"
python -m uvicorn app.main:app --host 127.0.0.1 --port $Port

# 一键起日常服务：先自检依赖（Docker/SearXNG/Ollama），再拉起 API。
# 用法：scripts\start-daily.ps1 [-Provider searxng|fixture] [-Port 8000]
[CmdletBinding()]
param(
    [ValidateSet("searxng", "fixture")][string]$Provider = "searxng",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$logDir = Join-Path $root "data/logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# 开机自启时没有窗口，日志是唯一线索
Start-Transcript -Path (Join-Path $logDir "start-daily.log") -Append | Out-Null

function Test-Endpoint([string]$Url) {
    try { return (Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 $Url).StatusCode -eq 200 } catch { return $false }
}

# 1) 已经在跑就不再起第二个
if (Test-Endpoint "http://127.0.0.1:$Port/api/health") {
    Write-Host "[skip] $Port 上已有 CleanSearch 在运行" -ForegroundColor Yellow
    exit 0
}

# 2) 依赖自检（只在真实搜索模式需要）
if ($Provider -eq "searxng") {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host "[warn] 找不到 docker，降级为固定样本模式" -ForegroundColor Yellow
        $Provider = "fixture"
    } else {
        $running = (docker ps --filter "name=cs-searxng" --format "{{.Names}}") -join ""
        if (-not $running) {
            Write-Host "[dep] 启动 SearXNG 容器" -ForegroundColor Cyan
            docker compose up -d searxng 2>&1 | Out-Null
        }
        for ($i = 0; $i -lt 45; $i++) {
            if (Test-Endpoint "http://127.0.0.1:8888/search?q=test&format=json") { break }
            Start-Sleep -Seconds 2
        }
        if (-not (Test-Endpoint "http://127.0.0.1:8888/search?q=test&format=json")) {
            Write-Host "[warn] SearXNG 90 秒内没就绪，降级为固定样本模式" -ForegroundColor Yellow
            $Provider = "fixture"
        }
    }
}

# 3) 本机模型只是加分项：连不上就提示，不阻断搜索
if (-not (Test-Endpoint "http://127.0.0.1:11434/api/tags")) {
    Write-Host "[warn] 本机 Ollama 未响应，AI 总结/翻译会失败；搜索不受影响" -ForegroundColor Yellow
}

# 4) 起 API（与手工启动同样的参数，日志写 data/logs）
Write-Host "[serve] provider=$Provider port=$Port" -ForegroundColor Green
& (Join-Path $root "scripts/serve.ps1") -Provider $Provider -Port $Port -SkipBuild
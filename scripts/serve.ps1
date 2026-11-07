# 发布形态：构建前端 -> FastAPI 单进程同源托管 API + 静态页
# 用法： .\scripts\serve.ps1                  （searxng）
#        .\scripts\serve.ps1 -Provider fixture （无需 Docker，固定样本三态）
[CmdletBinding(DefaultParameterSetName = "Ollama")]
param(
    [ValidateSet("searxng", "fixture")]
    [string]$Provider = "searxng",
    [int]$Port = 8000,
    [switch]$SkipBuild,
    [Parameter(ParameterSetName = "Ollama")][string]$OllamaModel,
    [Parameter(Mandatory, ParameterSetName = "DeepSeek")][switch]$DeepSeek
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

$modelEnv = @{}
if ($DeepSeek) {
    $keyPath = Join-Path $root "data/deepseek-api-key.txt"
    if (-not (Test-Path -LiteralPath $keyPath -PathType Leaf)) {
        throw "请先把 DeepSeek API 密钥保存到 data/deepseek-api-key.txt"
    }
    $key = [IO.File]::ReadAllText($keyPath).Trim()
    if (-not $key -or $key -match '[^\x21-\x7E]') {
        throw "data/deepseek-api-key.txt 应只包含一行 API 密钥"
    }
    $modelEnv = @{
        LLM_PROVIDER = "openai"
        LLM_BASE_URL = "https://api.deepseek.com"
        LLM_API_KEY = $key
        LLM_MODEL = "deepseek-flash"
        LLM_REASONING_EFFORT = "none"
    }
    Write-Host "[llm] 云端 DeepSeek: deepseek-flash" -ForegroundColor Cyan
} elseif ($OllamaModel) {
    $modelEnv = @{
        LLM_PROVIDER = "openai"
        LLM_BASE_URL = "http://127.0.0.1:11434/v1"
        LLM_API_KEY = "ollama"
        LLM_MODEL = $OllamaModel
        LLM_REASONING_EFFORT = $(if ($env:LLM_REASONING_EFFORT) { $env:LLM_REASONING_EFFORT } else { "none" })
    }
    Write-Host "[llm] 本机 Ollama: $OllamaModel" -ForegroundColor Cyan
}

$env:SEARCH_PROVIDER = $Provider
$env:API_PORT = "$Port"
$previous = @{}
try {
    foreach ($name in $modelEnv.Keys) {
        $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $modelEnv[$name], 'Process')
    }
    if ($Provider -eq "fixture") {
        Write-Host "[mode] 固定样本：test=有结果，__empty xxx=零结果，__fail xxx=上游不可用" -ForegroundColor Yellow
    }

    Write-Host "[serve] http://127.0.0.1:$Port" -ForegroundColor Green
    Set-Location "$root\apps\api"
    python -m uvicorn app.main:app --host 127.0.0.1 --port $Port
}
finally {
    foreach ($name in $previous.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
    }
}

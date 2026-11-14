# 打包成"下载即用"的 Windows 单目录发行版：python scripts/build-portable.ps1
# 产物：dist-portable/CleanSearch/（CleanSearch.exe + web/ + resources/ + data/ + 说明）
[CmdletBinding()]
param(
    [string]$OutDir = "dist-portable",
    [switch]$SkipWebBuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $SkipWebBuild) {
    Write-Host "[1/4] 构建前端" -ForegroundColor Cyan
    npm --prefix apps/web run build
    if ($LASTEXITCODE -ne 0) { throw "前端构建失败" }
}

$target = Join-Path $root $OutDir
Write-Host "[2/4] 打包 API 与启动器" -ForegroundColor Cyan
if (Test-Path $target) { Remove-Item -Recurse -Force $target }
New-Item -ItemType Directory -Force -Path $target | Out-Null

$fixtures = Join-Path $root "apps/api/fixtures"
$appAssets = Join-Path $root "apps/api/app"
python -m PyInstaller --noconfirm --clean --onedir --console --name CleanSearch     --distpath $target     --workpath (Join-Path $root "build-portable")     --specpath (Join-Path $root "build-portable")     --paths (Join-Path $root "apps/api")     --collect-submodules uvicorn     --add-data "$fixtures;fixtures" --add-data "$appAssets/db/schema.sql;app/db" --add-data "$appAssets/prompts;app/prompts" --collect-data tld     --collect-data trafilatura     --exclude-module tkinter     --exclude-module matplotlib     --exclude-module PyQt5     (Join-Path $root "packaging/launcher.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败" }

Write-Host "[3/4] 放前端产物与资源" -ForegroundColor Cyan
$app = Join-Path $target "CleanSearch"
Copy-Item -Recurse -Force (Join-Path $root "apps/web/dist") (Join-Path $app "web")
New-Item -ItemType Directory -Force -Path (Join-Path $app "resources") | Out-Null
Copy-Item -Force (Join-Path $root "apps/api/fixtures/blocklist.txt") (Join-Path $app "resources/blocklist.txt")
New-Item -ItemType Directory -Force -Path (Join-Path $app "data") | Out-Null

Write-Host "[4/4] 写说明与启动脚本" -ForegroundColor Cyan
$bat = @()
$bat += "@echo off"
$bat += "chcp 65001 >nul"
$bat += 'cd /d "%~dp0"'
$bat += 'start "" CleanSearch.exe'
Set-Content -Path (Join-Path $app "启动 CleanSearch.bat") -Value $bat -Encoding utf8

Copy-Item -Recurse -Force (Join-Path $root "packaging/searxng") (Join-Path $app "searxng")

# 让别的电脑也能一键建桌面快捷方式：随包带脚本 + 一个 bat
New-Item -ItemType Directory -Force -Path (Join-Path $app "tools") | Out-Null
Copy-Item -Force (Join-Path $root "scripts/create-shortcut.ps1") (Join-Path $app "tools/create-shortcut.ps1")

$shortcutBat = @()
$shortcutBat += "@echo off"
$shortcutBat += "chcp 65001 >nul"
$shortcutBat += 'cd /d "%~dp0"'
$shortcutBat += 'powershell -NoProfile -ExecutionPolicy Bypass -File "tools\create-shortcut.ps1" -Target "%~dp0CleanSearch.exe" -Name "CleanSearch"'
$shortcutBat += "pause"
Set-Content -Path (Join-Path $app "创建桌面快捷方式.bat") -Value $shortcutBat -Encoding utf8

$real = @()
$real += '@echo off'
$real += "chcp 65001 >nul"
$real += 'cd /d "%~dp0"'
$real += "where docker >nul 2>nul"
$real += "if errorlevel 1 ("
$real += "  echo 没找到 Docker。请先安装并启动 Docker Desktop，再运行本脚本。"
$real += "  echo 想先用离线固定样本模式，直接双击「启动 CleanSearch.bat」即可。"
$real += "  pause"
$real += "  exit /b 1"
$real += ")"
$real += "echo 正在启动随包附带的 SearXNG（首次会拉取镜像，约 1-2 分钟）..."
$real += "docker compose -f searxng\docker-compose.yml up -d"
$real += "if errorlevel 1 goto failed"
$real += "set SEARCH_PROVIDER=searxng"
$real += "set SEARXNG_URL=http://127.0.0.1:8891"
$real += "set SEARXNG_WAIT=1"
$real += 'start "" CleanSearch.exe'
$real += "exit /b 0"
$real += ":failed"
$real += "echo SearXNG 启动失败。看日志："
$real += "echo   docker compose -f searxng\docker-compose.yml logs --tail 50"
$real += "pause"
Set-Content -Path (Join-Path $app "启动 CleanSearch（真实搜索）.bat") -Value $real -Encoding utf8

$stop = @()
$stop += "@echo off"
$stop += 'cd /d "%~dp0"'
$stop += "docker compose -f searxng\\docker-compose.yml down"
$stop += "pause"
Set-Content -Path (Join-Path $app "停止 SearXNG.bat") -Value $stop -Encoding utf8

$readme = @()
$readme += "CleanSearch 免安装版（Windows x64）"
$readme += "================================="
$readme += ""
$readme += "怎么用"
$readme += "1. 解压全部文件到任意目录（路径里有中文也可以）。"
$readme += "2. 双击「启动 CleanSearch.bat」，或直接运行 CleanSearch.exe。"
$readme += "3. 浏览器会自动打开 http://127.0.0.1:8000/ ；没打开就手动访问。"
$readme += "4. 关掉命令行窗口即停止服务。"
$readme += ""
$readme += "默认是固定样本模式：不联网也能看到搜索、书签、总结界面。"
$readme += "书签库、令牌、图标缓存都在 data\ 目录，备份这个目录即可；换电脑整包拷过去就能继续用。"
$readme += ""
$readme += "想接真实搜索：装好并启动 Docker Desktop，双击「启动 CleanSearch（真实搜索）.bat」。"
$readme += "它会用包内 searxng\ 的 compose 起一个只绑 127.0.0.1:8891 的 SearXNG，再带 SEARCH_PROVIDER=searxng 启动。"
$readme += "不想要了就双击「停止 SearXNG.bat」。没有 Docker 也能用，只是停留在固定样本模式。"
$readme += "想接本机大模型总结：再加 LLM_BASE_URL / LLM_MODEL（OpenAI 兼容，如 Ollama 的 http://127.0.0.1:11434/v1）。"
$readme += ""
$readme += "常用环境变量"
$readme += "  API_PORT=8000                 换端口（被占用会自动挑空闲端口）"
$readme += "  ALLOWED_HOSTS=192.168.1.20    允许同一 Wi-Fi 下的手机访问（默认只允许本机）"
$readme += "  CLEANSEARCH_NO_BROWSER=1      启动时不自动开浏览器"
$readme += ""
$readme += "注意：只监听 127.0.0.1；手机装 PWA / 系统分享需要 HTTPS（明文下浏览器不注册 Service Worker）。"
$readme += "升级：用新版的 CleanSearch.exe、web\、resources\ 覆盖旧目录，保留 data\。"
Set-Content -Path (Join-Path $app "说明.txt") -Value $readme -Encoding utf8

Write-Host "[5/5] 打成 zip（排除运行时数据）" -ForegroundColor Cyan
$zip = Join-Path $target "CleanSearch-0.1.0-win-x64.zip"
if (Test-Path $zip) { Remove-Item -Force $zip }
Compress-Archive -Path $app -DestinationPath $zip -CompressionLevel Optimal -Force
Write-Host ("[完成] 发行目录：{0}   包：{1}（{2:N1} MB）" -f $app, $zip, ((Get-Item $zip).Length / 1MB)) -ForegroundColor Green
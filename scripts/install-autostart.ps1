# 开机自启（当前用户，无需管理员）：在「启动」文件夹放一个快捷方式，登录后隐藏窗口跑 scripts\start-daily.ps1。
# 用法：scripts\install-autostart.ps1 [-Port 8000] [-Provider searxng] [-Remove]
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [ValidateSet("searxng", "fixture")][string]$Provider = "searxng",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $root "scripts/start-daily.ps1"
$startup = [Environment]::GetFolderPath("Startup")
$link = Join-Path $startup "CleanSearch.lnk"

if ($Remove) {
    if (Test-Path -LiteralPath $link) { Remove-Item -LiteralPath $link -Force; Write-Host "[ok] 已移除开机自启：$link" -ForegroundColor Green }
    else { Write-Host "[skip] 没有找到 $link" -ForegroundColor Yellow }
    exit 0
}

if (-not (Test-Path -LiteralPath $script)) { throw "找不到 $script" }
$pwsh = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
if (-not $pwsh) { $pwsh = (Get-Command powershell).Source }

# 用「启动」文件夹而不是计划任务：ONLOGON 任务需要管理员，普通用户会被“拒绝访问”挡住
$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($link)
$sc.TargetPath = $pwsh
$sc.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`" -Provider $Provider -Port $Port"
$sc.WorkingDirectory = $root
$sc.WindowStyle = 7
$sc.Description = "CleanSearch 日常服务（登录时启动）"
$sc.Save()

Write-Host "[ok] 已加入开机自启：$link" -ForegroundColor Green
Write-Host "     立即试跑：Start-Process -FilePath `"$pwsh`" -ArgumentList `"-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`" -Provider $Provider -Port $Port`"" -ForegroundColor DarkGray
Write-Host "     移除：scripts\install-autostart.ps1 -Remove    日志：data\logs\start-daily.log" -ForegroundColor DarkGray
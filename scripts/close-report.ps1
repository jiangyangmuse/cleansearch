# 落定一份完工报告：先校验，再写结束时间/耗时，状态改为完成态，并更新台账
# 用法： .\scripts\close-report.ps1 -Path reports\xxx.md [-Status 完成|部分完成|阻塞]
# 退出码： 0 成功 / 1 校验未通过或文件缺失
[CmdletBinding()]
param(
    [string]$Path = "",
    [ValidateSet("完成", "部分完成", "阻塞")][string]$Status = "完成"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dir = Join-Path $root "reports"
$indexPath = Join-Path $dir "INDEX.md"

if (-not $Path) {
    $dirs = @($dir, (Join-Path $dir "incomplete"), (Join-Path $dir "completed"), (Join-Path $dir "uncategorized"))
    $cand = Get-ChildItem -LiteralPath $dirs -File -Filter "*.md" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}-\d{4}-' } |
        Sort-Object Name -Descending | Select-Object -First 1
    if (-not $cand) { Write-Host "[close] reports/ 下还没有报告" -ForegroundColor Red; exit 1 }
    $Path = $cand.FullName
}
if (-not (Test-Path $Path)) { Write-Host "[close] 文件不存在：$Path" -ForegroundColor Red; exit 1 }
$Path = (Resolve-Path $Path).Path
$fileName = [System.IO.Path]::GetFileName($Path)
$relativePath = $fileName
$parent = Split-Path -Parent $Path
if ((Split-Path -Parent $parent) -eq $dir) {
    $relativePath = "$(Split-Path -Leaf $parent)/$fileName"
}

# ---- 1. 先校验 ----
& (Join-Path $PSScriptRoot "check-report.ps1") -Path $Path
if ($LASTEXITCODE -ne 0) {
    Write-Host "[close] 校验未通过，未改动任何内容。补齐后重跑。" -ForegroundColor Red
    exit 1
}

# ---- 2. 写结束时间与耗时 ----
$text = [System.IO.File]::ReadAllText($Path)
$now = Get-Date
$endStamp = $now.ToString("yyyy-MM-dd HH:mm")

$start = $null
if ($text -match '\|\s*开始\s*\|\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s*\|') {
    try { $start = [datetime]::ParseExact($matches[1], 'yyyy-MM-dd HH:mm', [System.Globalization.CultureInfo]::InvariantCulture) } catch { $start = $null }
}
$dur = "—"
if ($start) {
    $span = $now - $start
    if ($span.TotalMinutes -lt 1) { $dur = "不到 1 分钟" }
    elseif ($span.TotalMinutes -lt 60) { $dur = ("{0:N0} 分钟" -f $span.TotalMinutes) }
    else { $dur = ("{0} 小时 {1} 分" -f [int][math]::Floor($span.TotalHours), $span.Minutes) }
}

if ($text -match '\|\s*结束\s*\|') { $text = $text -replace '\|\s*结束\s*\|[^|]*\|', "| 结束 | $endStamp |" }
if ($text -match '\|\s*耗时\s*\|') { $text = $text -replace '\|\s*耗时\s*\|[^|]*\|', "| 耗时 | $dur |" }
if ($text -match '\|\s*状态\s*\|') { $text = $text -replace '\|\s*状态\s*\|[^|]*\|', "| 状态 | $Status |" }
else { $text = $text.TrimEnd() + "`n" }

[System.IO.File]::WriteAllText($Path, $text, (New-Object System.Text.UTF8Encoding($false)))

# ---- 3. 更新台账 ----
if (-not (Test-Path $indexPath)) {
    Write-Host "[close] 警告：台账不存在，跳过登记：$indexPath" -ForegroundColor Yellow
} else {
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($l in [System.IO.File]::ReadAllLines($indexPath)) { $lines.Add($l) }

    $found = $false
    $reportPathPattern = '(?:[^/`]+/)?' + [regex]::Escape($fileName)
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match ('^\| \d{8}-\d{4} \|.*\| `' + $reportPathPattern + '` \|$')) {
            $lines[$i] = $lines[$i] -replace ('\(' + $reportPathPattern + '\)'), "($relativePath)"
            $lines[$i] = $lines[$i] -replace '\|[^|]*\| `[^`]+` \|$', "| $Status | ``$relativePath`` |"
            $found = $true
            break
        }
    }
    if (-not $found) {
        Write-Host "[close] 台账里没有这份报告，追加一行" -ForegroundColor Yellow
        $title = $fileName -replace '^\d{4}-\d{2}-\d{2}-\d{4}-', '' -replace '\.md$', ''
        $lines.Add("| $($now.ToString('yyyyMMdd-HHmm')) | $endStamp | [$title]($relativePath) | - | $Status | ``$relativePath`` |")
    }
    [System.IO.File]::WriteAllLines($indexPath, $lines, (New-Object System.Text.UTF8Encoding($false)))
}

Write-Host ""
Write-Host "[close] 报告：$Path" -ForegroundColor Green
Write-Host "[close] 结束=$endStamp  耗时=$dur  状态=$Status" -ForegroundColor Green
Write-Host "[close] 台账已同步：$indexPath" -ForegroundColor Green
Write-Host "[close] 最后一步：回复三行（做了什么 / 验证结果 / 下一个动作）" -ForegroundColor Cyan

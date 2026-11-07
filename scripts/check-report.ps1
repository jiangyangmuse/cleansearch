# 校验一份完工报告：必填段是否存在且非空、占位符是否清干净、命名与长度是否合规
# 用法： .\scripts\check-report.ps1 [-Path reports\xxx.md]    不给 Path 就校验最新一份
# 退出码： 0 通过 / 1 失败
[CmdletBinding()]
param(
    [string]$Path = "",
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dir = Join-Path $root "reports"

if (-not $Path) {
    $dirs = @($dir, (Join-Path $dir "completed"))
    $cand = Get-ChildItem -LiteralPath $dirs -File -Filter "*.md" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}-\d{4}-' } |
        Sort-Object Name -Descending | Select-Object -First 1
    if (-not $cand) { Write-Host "[check] reports/ 下还没有报告" -ForegroundColor Red; exit 1 }
    $Path = $cand.FullName
}
if (-not (Test-Path $Path)) { Write-Host "[check] 文件不存在：$Path" -ForegroundColor Red; exit 1 }
$Path = (Resolve-Path $Path).Path

$lines = [System.IO.File]::ReadAllLines($Path)
$text = ($lines -join "`n")

$problems = New-Object System.Collections.Generic.List[string]
$warns = New-Object System.Collections.Generic.List[string]

# 1) 文件命名
$name = [System.IO.Path]::GetFileName($Path)
if ($name -notmatch '^\d{4}-\d{2}-\d{2}-\d{4}-[a-z0-9][a-z0-9-]*\.md$') {
    $problems.Add("文件名不合规：$name（应为 YYYY-MM-DD-HHmm-<slug>.md）")
}

# 2) 模板占位符残留（先剥离围栏代码块与行内代码，避免正文引用被误判）
$prose = [regex]::Replace($text, '(?s)```.*?```', '')
$prose = [regex]::Replace($prose, '`[^`]*`', '')
if ($prose.Contains("{{")) { $problems.Add("还有未替换的模板占位符 {{...}}") }
if ($prose.Contains("〔待填〕")) { $problems.Add("还有未填写的〔待填〕占位，把每一处换成真实内容") }

# 3) 状态字段
if ($text -notmatch '\|\s*状态\s*\|\s*(\S+)\s*\|') { $problems.Add("头部表格缺少「状态」字段") }
elseif ($matches[1] -eq "进行中") { $warns.Add("状态仍是「进行中」，close-report 时会自动改成完成态") }

# 4) 长度
if ($lines.Count -gt 260) { $problems.Add("报告 $($lines.Count) 行，超过 260 行上限 —— 说明任务该拆") }

# 5) 必填段
$required = [ordered]@{ "1" = "任务"; "2" = "做了什么"; "3" = "改动清单"; "4" = "验证与证据"; "6" = "遗留与风险"; "7" = "交接" }

$sections = @{}
$order = New-Object System.Collections.Generic.List[string]
$current = $null
$buffer = New-Object System.Collections.Generic.List[string]
foreach ($line in $lines) {
    if ($line -match '^##\s+(.+)$') {
        if ($current) { $sections[$current] = $buffer.ToArray() }
        $current = $matches[1].Trim()
        $order.Add($current)
        $buffer = New-Object System.Collections.Generic.List[string]
        continue
    }
    if ($current) { $buffer.Add($line) }
}
if ($current) { $sections[$current] = $buffer.ToArray() }

foreach ($num in $required.Keys) {
    $hit = $order | Where-Object { $_ -match "^$num\s" } | Select-Object -First 1
    if (-not $hit) {
        $problems.Add("缺少必填段：## $num $($required[$num])")
        continue
    }
    $content = $sections[$hit] | Where-Object {
        $_.Trim() -ne "" -and $_ -notmatch '^\|\s*[-:|\s]+\|\s*$'
    }
    if (-not $content -or @($content).Count -eq 0) {
        $problems.Add("必填段为空：## $hit")
    }
}

# 6) 验证段要求至少有命令或明确写未验证
$verify = $order | Where-Object { $_ -match '^4\s' } | Select-Object -First 1
if ($verify) {
    $vtext = ($sections[$verify] -join "`n")
    if ($vtext -notmatch '未验证' -and $vtext -notmatch '`') {
        $warns.Add("验证段既没有命令也没有「未验证」说明，证据力度不足")
    }
}

# ---- 输出 ----
$ok = ($problems.Count -eq 0)
if (-not $Quiet) {
    Write-Host ""
    Write-Host "报告：$Path" -ForegroundColor Cyan
    if ($ok) { Write-Host "[check] PASS" -ForegroundColor Green }
    else { Write-Host "[check] FAIL" -ForegroundColor Red }
    foreach ($p in $problems) { Write-Host "  × $p" -ForegroundColor Red }
    foreach ($w in $warns) { Write-Host "  ! $w" -ForegroundColor Yellow }
}
if ($ok) { exit 0 } else { exit 1 }

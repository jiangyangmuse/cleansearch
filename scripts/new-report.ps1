# 起草完工报告：按 reports/_TEMPLATE.md 生成骨架，自动填时间 / 执行者 / 改动文件，并在台账登记一行
# 用法： .\scripts\new-report.ps1 -Slug m1-suffix-router -Type feat -Title "M1 后缀路由与 bang" -Goal "让 数分知识点 g 走 Google"
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Slug,
    [string]$Title = "",
    [ValidateSet("feat", "fix", "docs", "refactor", "test", "ops", "research")][string]$Type = "feat",
    [string]$Goal = "",
    [string]$Agent = "DSH/lead"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dir = Join-Path $root "reports"
$draftDir = Join-Path $dir "incomplete"
$templatePath = Join-Path $dir "_TEMPLATE.md"
$indexPath = Join-Path $dir "INDEX.md"

if ($Slug -notmatch '^[a-z0-9][a-z0-9-]{0,59}$') { throw "slug 只能是小写字母/数字/连字符，长度 1-60：$Slug" }
if (-not (Test-Path $templatePath)) { throw "缺少模板：$templatePath" }
if (-not (Test-Path $indexPath)) { throw "缺少台账：$indexPath" }
if (-not (Test-Path $dir)) { throw "缺少 reports 目录：$dir" }

$now = Get-Date
$id = $now.ToString("yyyyMMdd-HHmm")
$stamp = $now.ToString("yyyy-MM-dd HH:mm")
$fileName = "$($now.ToString('yyyy-MM-dd-HHmm'))-$Slug.md"
$path = Join-Path $draftDir $fileName
$locations = @($dir, $draftDir, (Join-Path $dir "completed"), (Join-Path $dir "uncategorized"))
foreach ($location in $locations) {
    $existing = Join-Path $location $fileName
    if (Test-Path -LiteralPath $existing) { throw "报告已存在：$existing —— 同一任务请追加到原报告（## 8 追加轮次），不要新建" }
}
if (-not $Title) { $Title = ($Slug -replace '-', ' ') }

# ---- 采集改动文件：优先 git，没有仓库就按近 6 小时修改时间 ----
$rows = New-Object System.Collections.Generic.List[string]
if (Test-Path (Join-Path $root ".git")) {
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) {
        Push-Location $root
        try { $status = & git status --porcelain } finally { Pop-Location }
        foreach ($line in $status) {
            if (-not $line.Trim() -or $line.Length -lt 4) { continue }
            $code = $line.Substring(0, 2).Trim()
            $rel = $line.Substring(3).Trim().Trim('"')
            $kind = switch ($code) { "??" { "新增" } "A" { "新增" } "D" { "删除" } "M" { "修改" } default { $code } }
            $rows.Add("| ``$rel`` | $kind | 自动采集（git） |")
        }
    }
}
if ($rows.Count -eq 0) {
    $cut = (Get-Date).AddHours(-6)
    $skip = '[\\/](node_modules|dist|\.pytest_cache|__pycache__|\.git|\.venv|htmlcov)[\\/]|\.egg-info[\\/]'
    $exts = @(".ps1", ".md", ".py", ".ts", ".tsx", ".json", ".yml", ".yaml", ".css", ".html", ".txt")
    Get-ChildItem $root -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -gt $cut -and $_.FullName -notmatch $skip -and $exts -contains $_.Extension } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 25 | ForEach-Object {
            $rel = $_.FullName.Substring($root.Length + 1)
            $rows.Add("| ``$rel`` | 修改 | 自动采集（近 6 小时，按修改时间倒序前 25 个） |")
        }
}
if ($rows.Count -eq 0) { $rows.Add("| — | — | 本次未产生文件改动 |") }

# ---- 生成报告 ----
[System.IO.Directory]::CreateDirectory($draftDir) | Out-Null
$body = [System.IO.File]::ReadAllText($templatePath)
$body = $body.Replace("{{TITLE}}", $Title).Replace("{{ID}}", $id).Replace("{{START}}", $stamp).Replace("{{AGENT}}", $Agent).Replace("{{TYPE}}", $Type).Replace("{{GOAL}}", $(if ($Goal) { $Goal } else { "〔待填〕一句话写清要达成什么" })).Replace("{{CHANGED_ROWS}}", ($rows -join "`n"))
[System.IO.File]::WriteAllText($path, $body, (New-Object System.Text.UTF8Encoding($false)))

# ---- 台账登记：新行插在表头分隔线之后 ----
$lines = New-Object System.Collections.Generic.List[string]
foreach ($l in [System.IO.File]::ReadAllLines($indexPath)) { $lines.Add($l) }
$insertAt = -1
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i].Trim() -match '^\|\s*-{3,}') { $insertAt = $i + 1; break }
}
$relativePath = "incomplete/$fileName"
$row = "| $id | $stamp | [$Title]($relativePath) | $Type | 进行中 | ``$relativePath`` |"
if ($insertAt -ge 0) { $lines.Insert($insertAt, $row) } else { $lines.Add($row) }
[System.IO.File]::WriteAllLines($indexPath, $lines, (New-Object System.Text.UTF8Encoding($false)))

Write-Host "[new-report] 报告：$path" -ForegroundColor Green
Write-Host "[new-report] 台账：$indexPath（已插入一行，状态=进行中）" -ForegroundColor Green
Write-Host "[new-report] 下一步：填满 §1-§7，然后 close-report.ps1 -Path `"$path`"" -ForegroundColor Cyan

# M0–M2 冒烟：搜索三态 + 分档 + 拦截 + 总结及引用 + 同源首页
# 用法： .\scripts\smoke.ps1 [-BaseUrl http://127.0.0.1:8000]
param([string]$BaseUrl = "http://127.0.0.1:8000")

$ErrorActionPreference = "Stop"
$results = @()
function Check($name, $ok, $detail) {
    $script:results += [pscustomobject]@{ Check = $name; Pass = $ok; Detail = $detail }
}
function Post($body) {
    Invoke-RestMethod "$BaseUrl/api/search" -Method Post -ContentType "application/json" -Body $body
}

$health = Invoke-RestMethod "$BaseUrl/api/health"
Check "health 200" ($health.status -eq "ok") "provider=$($health.provider) web_built=$($health.web_built) blocklist=$($health.blocklist_rules)"

$hit = Post '{"q":"python 文档"}'
Check "有结果" ($hit.meta.status -eq "ok" -and $hit.meta.upstream_total -ge 10) "total=$($hit.meta.total) upstream=$($hit.meta.upstream_total)"

$groups = "$($hit.groups.strong.Count)/$($hit.groups.related.Count)/$($hit.groups.weak.Count)"
Check "三档分组" ($hit.groups.strong.Count -ge 1 -and $hit.groups.related.Count -ge 1 -and $hit.groups.weak.Count -ge 1) "strong/related/weak=$groups"

$cachedHit = Post '{"q":"python 文档"}'
Check "缓存命中" ($cachedHit.meta.cached -eq $true) "cached=$($cachedHit.meta.cached) total=$($cachedHit.meta.total)"

$routed = Post '{"q":"python 文档 g"}'
Check "后缀路由" ($routed.parsed.engine -eq "google" -and $routed.parsed.router -eq "suffix") "engine=$($routed.parsed.engine) router=$($routed.parsed.router) q=$($routed.parsed.q)"

$guarded = Post '{"q":"C g"}'
Check "C g 不误触发" ($guarded.parsed.router -eq "default") "router=$($guarded.parsed.router)"

$risky = Post '{"q":"账号验证","opts":{"fixture":"risky"}}'
Check "黑名单拦截" ($risky.meta.filtered.risk -eq 1) "filtered.risk=$($risky.meta.filtered.risk) upstream=$($risky.meta.upstream_total)"

$empty = Post '{"q":"test","opts":{"fixture":"empty"}}'
Check "零结果" ($empty.meta.status -eq "empty" -and $empty.meta.total -eq 0) "total=$($empty.meta.total)"

$failCode = $null
try { Post '{"q":"test","opts":{"fixture":"error"}}' | Out-Null }
catch { $failCode = ($_.ErrorDetails.Message | ConvertFrom-Json).error.code }
Check "上游不可用" ($failCode -eq "UPSTREAM_UNAVAILABLE") "code=$failCode"

# 两种模型模式都必须有正文、正确引用和正常结束。
$sid = $hit.meta.sid
$sse = Invoke-WebRequest "$BaseUrl/api/summarize?sid=$sid&mode=fast" -UseBasicParsing -TimeoutSec 60
$events = @([regex]::Matches($sse.Content, '(?m)^event: (\w+)\r?\ndata: ([^\r\n]+)') | ForEach-Object {
    [pscustomobject]@{ Name = $_.Groups[1].Value; Data = ($_.Groups[2].Value | ConvertFrom-Json) }
})
$cites = @($events | Where-Object Name -eq "cite")
$tokens = @($events | Where-Object Name -eq "token")
$errors = @($events | Where-Object Name -eq "error")
$resultIds = (@($hit.groups.strong) + @($hit.groups.related) + @($hit.groups.weak)).id
$invalidCites = @($cites | Where-Object { $_.Data.result_id -notin $resultIds })
$text = ($tokens | ForEach-Object { $_.Data.t }) -join ""
$references = @([regex]::Matches($text, '\[([0-9]+)\]') | ForEach-Object { $_.Groups[1].Value })
$invalidReferences = @($references | Where-Object { $_ -notin $cites.Data.i })
$sseOk = ($events.Count -ge 4 -and $events[0].Name -eq "meta" -and
    $events[0].Data.model -eq $health.llm_model -and $events[-1].Name -eq "done" -and
    $errors.Count -eq 0 -and $cites.Count -gt 0 -and $invalidCites.Count -eq 0 -and
    $references.Count -gt 0 -and $invalidReferences.Count -eq 0)
$summaryDetail = "provider=$($health.llm_provider) model=$($health.llm_model) cites=$($cites.Count) chunks=$($tokens.Count)"
if ($errors.Count) { $summaryDetail += " error=$($errors[0].Data.code)" }
Check "侧栏总结 SSE" $sseOk $summaryDetail

$badSid = $null
try { Invoke-WebRequest "$BaseUrl/api/summarize?sid=s_none&mode=fast" -UseBasicParsing | Out-Null }
catch { $badSid = [int]$_.Exception.Response.StatusCode }
Check "过期快照 404" ($badSid -eq 404) "status=$badSid"

# 书签（M3）：只读检查，不写入用户数据
$bookmarks = Invoke-RestMethod "$BaseUrl/api/bookmarks?limit=1"
$pageCount = @($bookmarks.items).Count
Check "书签接口" ($null -ne $bookmarks.total -and $null -ne $bookmarks.fts -and $pageCount -eq [Math]::Min(1, $bookmarks.total)) "total=$($bookmarks.total) returned=$pageCount groups=$(@($bookmarks.groups).Count) fts=$($bookmarks.fts)"

$exported = Invoke-WebRequest "$BaseUrl/api/bookmarks/export" -UseBasicParsing
Check "书签导出" ($exported.Content -match "NETSCAPE-Bookmark-file-1") "bytes=$($exported.RawContentLength)"

# 正文抓取（M4）：内网地址必须在不联网的情况下被拒
$ssrf = $null
try {
    Invoke-RestMethod "$BaseUrl/api/page/summarize" -Method Post -ContentType "application/json" -Body '{"url":"http://169.254.169.254/latest/meta-data/"}' | Out-Null
    $ssrf = 200
} catch { $ssrf = [int]$_.Exception.Response.StatusCode }
Check "内网地址拦截" ($ssrf -eq 403) "status=$ssrf"

# 跨域写书签：没有 token 必须被拒
$corsStatus = $null
try {
    Invoke-RestMethod "$BaseUrl/api/bookmarks" -Method Post -ContentType "application/json" -Headers @{ Origin = "https://evil.example" } -Body '{"url":"https://blocked.test/a"}' | Out-Null
    $corsStatus = 200
} catch { $corsStatus = [int]$_.Exception.Response.StatusCode }
Check "跨域 token 拦截" ($corsStatus -eq 401) "status=$corsStatus"

$page = Invoke-WebRequest "$BaseUrl/" -UseBasicParsing
Check "同源首页" ($page.StatusCode -eq 200 -and $page.Content -match 'id="root"') "bytes=$($page.RawContentLength)"

$results | Format-Table -AutoSize
if ($results.Pass -contains $false) { Write-Host "冒烟失败" -ForegroundColor Red; exit 1 }
Write-Host "冒烟通过" -ForegroundColor Green
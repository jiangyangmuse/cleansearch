# 完工报告 · M4 受控抓取与正文增强验收

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261106-2003 |
| 开始 | 2026-11-06 20:03 |
| 结束 | 2026-11-06 20:06 |
| 耗时 | 3 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 完成 |

## 1 任务

**目标**

验收 M4 正文增强、单页总结和死链检测，修复可复现的抓取边界和误判。

**验收标准**

- 抓取只能连接已验证地址，每跳校验。DNS、重定向、读取共用总时限。
- 单页总结和增强在正常、部分降级和失败时给出对应结果。死链检测区分失效和暂无法确认。
- 全量测试、前端构建、固定样本冒烟和浏览器关键操作通过。用本机千问验证真实单页总结。

**不做**

- 本轮范围为 M4 的已有入口与护栏。公开联网探针使用 Python 官方文档，书签写入使用临时库。

## 2 做了什么

1. 固定每跳的连接 IP，保留 HTTP Host 与 TLS 域名校验，拒绝共享地址、IPv6 过渡地址和非公网地址。仅保留本机透明代理的受限例外。
2. DNS、跳转和读正文共用时限。正文严格校验媒体类型和字节数，拒绝压缩响应。死链检测复用受控连接，仅读取状态。
3. 死链检测按当前页书签 ID 执行。404/410 才标记失效，限流、超时、安全拒绝只显示无法确认。一次事务更新确定状态。
4. 正文增强给每条引用标注素材类型，部分失败或截断仍可生成并明确标记。单页总结区分抓取和模型错误，调整千问输出格式，兼容模型给出一整段的情况。

## 3 改动清单

| 路径 | 说明 |
| --- | --- |
| `apps/api/app/core/fetch.py` | DNS 地址固定、整体时限、媒体和正文限额、状态探测 |
| `apps/api/app/core/session_store.py`、`apps/api/app/core/summarize.py`、`apps/api/app/routers/summarize.py` | 引用素材标记、部分降级、取消与耗时语义 |
| `apps/api/app/routers/page.py` | 单页错误分类、使用最终地址和要点解析 |
| `apps/api/app/db/repo.py`、`apps/api/app/routers/bookmarks.py` | 按 ID 检查、状态判定及批量更新 |
| `apps/web/src/api.ts`、`apps/web/src/BookmarkPage.tsx`、`apps/web/src/components/SummaryPanel.tsx` | 当前页检测、未知状态计数、引用素材说明 |
| `apps/api/tests/test_fetch.py`、`test_bookmarks.py`、`test_content.py` | 抓取、状态、降级和单页回归 |
| `README.md`、`.env.example`、`docs/决策与接口变更.md` | 接口和本机透明代理行为 |
| `reports/2026-11-06-2003-m4-fetch-acceptance.md`、`reports/INDEX.md` | 验收证据和台账 |

## 4 验证与证据

| 命令或操作 | 结果 | 关键输出 |
| --- | --- | --- |
| `python -m pytest apps/api -q -o 'addopts='` | 通过 | 最终版 `213 passed in 1.40s`。包含 DNS 钉扎及 TLS Host/SNI、DNS/滴流超时、压缩拒绝、PDF 存活、老书签 ID、部分降级、单页超时和要点拆分 |
| `npm --prefix apps/web run build` | 通过 | TypeScript 通过，Vite 转换 39 个模块，775 ms |
| Python 离线探针 `SafeFetcher(timeout=.06, resolver=…, transport=httpx.MockTransport(...))` | 通过 | 改前：`100.64.0.1` 放行、连接仍用域名、滴流 0.140 秒完成。改后：共享地址拒绝、连接目标 `93.184.216.34`、约 0.065 秒返回 `FetchTimeout` |
| Python `SafeFetcher.fetch('https://docs.python.org/3/library/asyncio.html')`，分别使用默认策略和 `extra_cidrs=('198.18.0.0/15',)` | 通过 | 默认拒绝本机解析出的 `198.18.0.186`。显式透明代理例外下通过 TLS 验证并返回 HTTP 200、`text/html`、25411 字节、1.677 秒 |
| 设置临时 `DB_PATH`、`LLM_PROVIDER=stub` 与 `FETCH_EXTRA_CIDRS=198.18.0.0/15`，运行 `.\scripts\serve.ps1 -Provider fixture -Port 18093 -SkipBuild` | 通过 | 本机隔离实例启动 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18093` | 通过 | 14/14，内网地址拦截 403，摘要 SSE 161 片段，书签导出与同源页面通过 |
| `httpx` 调用 `/api/page/summarize`、`/api/bookmarks/check`、`/api/summarize?mode=full` | 通过 | 单页首次实网抓取 504，复测 200、标准库提取 341 字。书签 `checked=3 dead=1 unknown=1`（200、404、回环拒绝）。正文增强 HTTP 探针 5 条成功、5 条未尝试增强并保留摘要，169 片段，`partial=false` |
| 内置浏览器在 18093 执行共享地址总结、正文增强和「检测本页死链」 | 通过 | 页面显示拒绝 `100.64.0.1`；另一轮实际抓取 1 条、降级 4 条，引用分别标注「正文节选」或「搜索摘要」。书签页显示 3 条中 1 条失效、1 条暂无法确认 |
| 设置透明代理例外，运行 `.\scripts\serve.ps1 -Provider fixture -Port 18095 -OllamaModel 'qwen3.5-4b-local:latest' -SkipBuild`，对同一官方文档 `POST /api/page/summarize` | 通过 | 本机千问初测 200 但要点数为 0。修改单页提示与解析后复测 200、341 字正文、一句结论与 2 条要点，端到端 12.17 秒 |

证据为以上终端、HTTP 探针及浏览器无障碍树摘要。验收服务仅监听本机回环。

## 5 关键决策

| 决策 | 依据 |
| --- | --- |
| 连接固定到已校验 IP，TLS 继续核对原域名 | 消除 DNS 验证到连接之间的重绑定窗口。[HTTPCore SNI 扩展](https://www.encode.io/httpcore/extensions/#sni_hostname) · [OWASP SSRF 指南](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) |
| 单次抓取共享总时限 | 某一阶段持续小流量或多次跳转不能一直占用请求 |
| 仅确定状态写入书签 | 避免把登录、限流、暂时故障、拦截和合法二进制链接当成死链 |

## 6 遗留与风险

- 本机公网 DNS 走透明代理，本轮实网成功路径使用了临时例外。默认策略拦截已验收，直连公网环境仍待复验。
- 真实网页速度有波动，实际浏览器发生过部分降级。只覆盖了标准库正文提取路径，trafilatura 可选路径及 JS 渲染页面未验。
- 正文抓取拒绝强制压缩的响应。该类站点在增强模式会保留搜索摘要。

## 7 交接

用未设置 `FETCH_EXTRA_CIDRS` 的公网直连环境跑一次单页与增强，并对照 trafilatura 提取结果。需要复现本机模式时，只在当前进程为透明代理设置 `FETCH_EXTRA_CIDRS=198.18.0.0/15`。

- `docs/决策与接口变更.md` 的「M4 验收修正」记录接口语义和策略。
- `apps/api/tests/test_fetch.py`、`test_content.py`、`test_bookmarks.py` 包含本轮回归。

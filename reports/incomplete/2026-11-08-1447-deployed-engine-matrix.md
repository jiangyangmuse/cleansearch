# 完工报告 · 部署更新与十三引擎在线复验

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261108-1447 |
| 开始 | 2026-11-08 14:47 |
| 结束 | 2026-11-08 15:08 |
| 耗时 | 22 分钟 |
| 执行者 | Codex |
| 任务类型 | test |
| 状态 | 部分完成 |

## 1 任务

**目标**：执行上轮下一动作，让当前修复在实际部署生效，补跑十三引擎在线矩阵。

**已达成**：重启实际原生 API、保持既有 DB/token/模型配置；十三首屏、十三第二页和两次缓存复查全部执行；核对实际来源并记录不可用项；真实页面验证 DeepSeek 根入口。

**未达成**：十三首屏全部有结果（当前 11/13）；完整 Compose 默认端口启动（被既有原生服务占用）。因此本报告为部分完成，留在 reports 根目录。

**不做**：不提交/推送；不更改排序或回退策略；不清除熔断制造通过；不合并原生与 Docker 书签库；不把 Chromium 尺寸模拟当 Chrome/Android 真机。

## 2 做了什么

1. 读取台账最近三份、决策及共享交接；开工 HEAD `997797e`，工作区初始干净，确认 DSH 已发布上一轮 M19/NAV。
2. 前端构建通过，启动 Docker Desktop；备份原 Docker 书签库（2 书签、1 分组）和原生库，记录表/token 摘要，不输出真实行或密钥。
3. API 镜像构建成功；`docker compose up -d --build --force-recreate` 启动阶段遇 8888 冲突。最初受限 Get-NetTCPConnection 漏报，直接 HTTP 与 psutil 确认本项目原生 API/SearXNG 已运行，未抢占端口或迁移数据库。
4. 原生 API 23852→40792 重启后，另一执行体修改健康读取并主动结束 40792、启动 17620，第一次矩阵在第八项连接重置。按 AGENTS 停止共享变更并询问协调；用户明确选择“让另一执行体先收口，再由本轮继续验收”。
5. 读取 M19 §9 的完成记录（363 测试、最新 API 重启），等待其收口后再行动；17620→13796，保留原生 `data/review-temp/verify.db`（0 书签）和 token，缓存按项目 `.env` 恢复 true，其余环境沿用。
6. 完整矩阵执行 28 次请求：13 首屏、2 缓存复查、13 第二页。首屏 11/13；主源 9 路，回退 2 路；Mojeek 冷却阻断 mj/sp，保留失败证据。矩阵脚本因未达 13/13 返回 1，未伪装全通过。
7. 17 引擎×2 查询的直接探测核对指定来源，旧四个假阳性均计 0。发现未加载引擎仍会触发默认聚合，新增 /config 预检；四源复跑 search_requests=0，补 2 项回归。
8. 健康读取修复纳入新镜像后再次构建；镜像关键源码指纹与当前工作区相同，隔离 fixture 容器两套冒烟通过并清理。
9. 未打桩的真实 Chromium 搜索 deepseek：上游 65、展示 16，www.deepseek.com 根入口默认可见，chat.deepseek.com 保留，重复命中缓存，390px 无横向溢出。
10. README、进度、决策 M19-A、原 M19 §10 及台账同步；保留另一执行体全部改动，不替其提交。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `scripts/probe-engines.py` | 修改 | /config 加载状态预检；catalog_checked/search_requests/skipped 输出 |
| `apps/api/tests/test_engine_probe.py` | 修改 | 未加载时不发搜索；坏目录保持未知的两项回归 |
| `README.md`、`docs/进展与欠账.md`、`docs/决策与接口变更.md` | 修改 | 当前可用范围、端口限制、M19-A 决策 |
| `reports/2026-11-08-1137-m19-engine-suffix-repair.md` | 追加 | 只加 §10；保留 DSH §9 与其它历史正文 |
| 本报告与 `reports/INDEX.md` | 新增/更新 | 部分完成、当前进度对齐 |
| `reports/assets/deployed-engine-matrix/` | 新增 | 矩阵/浏览器/快照脚本、JSON、JUnit、构建和冒烟日志、截图 |
| `apps/web/dist/`、本机进程与镜像 | 本地运行产物 | 前端 44 modules；原生 API 重启并恢复缓存；镜像重建，均未提交 |

本轮没有编辑 `core/breaker.py`、`routers/engines.py`、`tests/test_breaker.py`；它们是另一执行体 §9 的并发修复。NAV normalize/cache 实现保持原样。

## 4 验证与证据

Windows 测试临时目录：`$env:TEMP = Join-Path $PWD 'data/review-temp'; $env:TMP = $env:TEMP`。所有真实查询为公开验收词；书签仅只读核对。

| 命令原文 | 真实结果与摘要 |
| --- | --- |
| `npm --prefix apps/web run build` | 退出 0，tsc + Vite，44 modules，JS 266.24 kB/gzip 83.83 kB |
| `docker desktop start --detach` | 引擎启动，ServerVersion 29.9.2 |
| `python reports/assets/deployed-engine-matrix/snapshot-deploy.py --out reports/assets/deployed-engine-matrix/data-before.json --backup-dir data/deploy-backup-20261108-1447` | 原卷备份成功；2 书签/1 分组/0 tag；token 存在，只记录摘要 |
| `docker compose up -d --build --force-recreate` | 退出 1：镜像构建成功，容器启动时 127.0.0.1:8888 bind 冲突；已有原生 SearXNG，不判 Compose 通过 |
| `python reports/assets/deployed-engine-matrix/restart-native.py` | 23852→40792，首轮启动健康，后被另一执行体重启；中断结果另存 |
| `python scripts/probe-engines.py --base-url http://127.0.0.1:8888 --engines bing duckduckgo yahoo mojeek 'google cse' naver yandex swisscows wikipedia google 'google scholar' sogou 360search startpage marginalia dogpile 'yandex api' --json-out reports/assets/deployed-engine-matrix/direct-probe.json` | 17×2 直接探测执行；10 引擎 2/2 有指定来源；四个默认聚合源成功数为 0；Wikipedia 本组长查询为正常空态 |
| `python reports/assets/deployed-engine-matrix/restart-native.py --label final --restore-cache` | 17620→13796，19 目录项，CACHE_ENABLED=true，原 DB 路径保留 |
| `python reports/assets/deployed-engine-matrix/verify-matrix.py --base-url http://127.0.0.1:8000` | 退出 1：11/13 首屏有结果，9 主源/2 回退；28 次检查无契约异常，但可用性门槛未全达成 |
| `docker compose build api` | 退出 0；纳入 §9 最新健康修复，日志 image-build.txt；运行容器内五份关键代码 SHA256 与工作区一致 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18174` | 新镜像隔离 fixture，16/16；搜索/缓存/安全/总结/书签/首页全通过 |
| `python scripts/ci-smoke.py http://127.0.0.1:18174` | 同一新镜像 fixture，15/15，退出 0 |
| `python -m pytest apps/api -q -o 'addopts=' --junitxml=reports/assets/deployed-engine-matrix/api-tests.xml` | 初次独立复核 §9：363 passed in 8.71s；新增探测回归后最终 **365 passed in 8.98s** |
| `python scripts/probe-engines.py --base-url http://127.0.0.1:8888 --engines startpage marginalia dogpile 'yandex api' --json-out reports/assets/deployed-engine-matrix/guarded-probe.json` | 4 源都 catalog_checked=true、skipped=not_loaded、search_requests=0；未发默认聚合搜索 |
| `node reports/assets/deployed-engine-matrix/verify-browser.cjs` | 真实 API，官网根入口默认可见、聊天候选保留、缓存命中、390px 无横向溢出、无 pageerror；退出 0 |
| `python reports/assets/deployed-engine-matrix/snapshot-deploy.py --read-volume --out reports/assets/deployed-engine-matrix/data-after.json` | 只读挂载原 llq_bookmarks，表/token 摘要与重建前完全一致；原生库及 token 另比对一致 |
| `docker stop cs-deploy-fixture` | 本轮临时容器停止并自动移除；8000/8888 原生服务保留 |

### 首屏结果（本次时点）

| 后缀 | 来源 / 状态 | 展示数 |
| --- | --- | --- |
| b | bing | 10 |
| d | duckduckgo | 10 |
| y | yahoo | 7 |
| mj | 503，Mojeek 冷却阻断 | 0 |
| gc | google cse | 13 |
| n | naver | 16 |
| yd | yandex | 10 |
| sw | swisscows | 10 |
| w | wikipedia | 1 |
| g | google cse | 13 |
| sc | serper | 9 |
| sg | sogou | 9 |
| sp | 503，Mojeek 冷却阻断 | 0 |

第二页 8 路有结果、b/w 合法空态、mj/sc/sp 三路 503；成功结果来源均在各自目录允许集合内，未返回 serper/brave。缓存复查 b/g 都 cached=true。第二页无计费的调用次数由 Mock 契约覆盖，本轮网络响应仅证明没有付费来源，不能据此精确推算账单。

证据：[目录](../assets/deployed-engine-matrix/)。重点文件：`api-matrix.json`（完整）、`api-matrix-interrupted.json`（中断）、`direct-probe.json`、`guarded-probe.json`、`api-tests.xml`、`browser-first.json`（冷）、`browser.json`（热且严格只认 www/root）、`live-desktop.png`、`live-mobile.png`、`data-preservation.json`、`services.json`、`image-code-hashes.json`、`smoke-image*.txt`。

未验证：Mojeek 当前冷却结束后的恢复、全部 13 首屏有结果、完整 Compose 默认端口运行、正式 Chrome/Android；本轮未跑真实 LLM 生成或新远端 CI。fixture 使用 stub，真实浏览器使用原生 API，不拦截/替换响应。CLI 控制台部分中文编码替换，JSON/XML 为 UTF-8，可核对原文。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 保留原生实际部署 | 强行终止原生并切到 Compose | 两套库不同，不能借验收无意迁移用户存储 |
| 遇并发冲突先协调 | 反复互相重启 API | 用户明确选择先等对方收口，避免语义与服务状态冲突 |
| 预检未加载源 | 直接发请求后只过滤来源 | 虽可防假阳性，仍会向默认上游制造额外访问 |
| 保留 11/13 和冷却证据 | 清熔断或换查询凑 13/13 | 当前可用性与既定契约须分别记录，不能修改状态制造通过 |

配置预检属于验收脚本变化，无公开 API 结构变化；决策见 M19-A。

## 6 遗留与风险

- **待补 mj/sp**：Mojeek 的 app 冷却在矩阵结束时余约 55 分钟，默认聚合另记录 Suspended: access denied。早先直接探测 2/2 成功不代表此后持续可用。待自然冷却并且上游恢复后再补两项，不人为清状态。
- **完整 Compose 待切换**：cs-api/cs-searxng 创建但未启动，镜像已更新。原生继续占用 8000/8888；如需容器运行，先明确切换方式或改端口，保留 llq_bookmarks，勿 down -v。
- 原生仍用既有 `data/review-temp/verify.db`，0 书签；Docker llq_bookmarks 有 2 书签、1 分组。两套存储不同，均备份且未合并，不能把它们的数量差解释为丢失。
- 原生 PID 13796/SearXNG 36688 保持运行，缓存 true。临时 fixture 已移除，Docker Desktop 为构建启动并保留；没有修改开机启动策略。
- 工作区包含另一执行体尚未提交的健康修复与本轮探测增量；HEAD 仍为 997797e，本轮未 commit/push。镜像源码匹配本机当前文件，不代表远端已发布。
- 本报告状态部分完成，不归档；原 M19 保留历史头部并追加 §10，更正可用范围，不回写旧测试数。

## 7 交接

**下一个人第一件事**：确认 Mojeek 自然冷却结束、/config 仍加载该源后，只补 mj/sp 的真实首屏/第二页并记录来源；若仍限流，保留失败并评估回退方案，不直接重跑全量制造额外访问。

**运行入口**：[本机页面](http://127.0.0.1:8000/)；原生 SearXNG 为 8888。Compose 需另做端口/存储方式切换确认。

**相关文件**：[进展与欠账](../../docs/进展与欠账.md)、[决策](../../docs/决策与接口变更.md)、[原 M19 §9/§10](2026-11-08-1137-m19-engine-suffix-repair.md)。本轮验证脚本在资产目录，重启脚本仅用于经核对的本机原生部署，不能盲目在其他机器执行。

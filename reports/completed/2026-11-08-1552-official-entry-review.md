# 完工报告 · 官方入口复核与交互缓存完善

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261108-1552 |
| 开始 | 2026-11-08 15:52 |
| 结束 | 2026-11-08 16:04 |
| 耗时 | 13 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 完成 |

## 1 任务

目标：审查 DSH 已完成的官方入口表与独立分区，修复可复现缺陷并完善使用体验。
验收：认证边界、意图、去重、冷热缓存、风险确认与引用闭环有回归；API 全量、前端构建、fixture 冒烟与浏览器验证通过。
不做：不修改引擎回退/熔断、打分权重或品牌主机清单；不提交推送、不替换日常部署，不把固定样本验收算成真实上游/模型或正式 Chrome/Android 验收。

开工读取 INDEX 最近三份、决策与 DSH 报告。上一轮新增 46 品牌/112 入口、33 测试，398 项历史通过；8000 旧进程未加载功能，总结引用与移动端尚未完整验收。

## 2 做了什么

1. 补 20 项复核回归，原实现 16 失败/4 通过：内容查询误判导航；documentation 反而被排除；路径回退/编码歧义、HTTP/非默认端口被认证；缓存丢 ID/摘要；官方长标题文档被第三方吞并；官方入口丢风险确认。
2. 身份限定声明 HTTPS 默认端口，拒绝路径回退、重复分隔或编码歧义。仅单一品牌与导航词组成的查询展示官方区，苹果派、微信小程序开发、语法与多品牌查询保持普通排序。
3. 精确去重后保护官方入口，再对普通候选做标题去重，官方和普通候选仍共同参与原打分。OfficialLink 继承完整 Result，缓存保留原始 ID、摘要、风险信息；官方来源排在总结快照前列，冷/热 SSE cite 的 ID/URL 一致。
4. 每次响应重新为普通与官方结果生成 go_url；缓存不持久化签名。目录/别名/路径/核验信息摘要加入 official-v2 命名空间，目录撤销自动失配旧缓存，search-v6 不变。
5. 官方入口补收藏、j/k/Enter/b 键盘、引用定位和选择状态；收藏按钮与普通卡片共用实现。窄屏入口独立换行，页面展示数改为 meta.total + meta.official，接口仍保持 total 只计三档。
6. 核验脚本先查最终 HTTPS 来源，再区分受限，仅 2xx 算 ok；新增 8 项边界回归与 1 项目录缓存回归，共增加 29 项测试。旧 112 条证据离线重放仍为 107 ok/5 blocked/0 fail，未重新联网核验身份。
7. 新增决策 OFFICIAL-R1～R7、README 与进度复核说明；独立报告记录差异，未删改 DSH 原报告与历史状态。

## 3 改动清单

| 路径 | 改动 |
| --- | --- |
| apps/api/app/core/official.py | 意图、协议端口路径边界、完整结果字段、目录缓存摘要 |
| apps/api/app/schemas.py | OfficialLink 继承 Result |
| apps/api/app/routers/search.py | 保护入口、快照优先级、缓存引用、风险链接 |
| apps/api/tests/test_official_review.py | 新增 29 项回归 |
| apps/web/src/components/OfficialPanel.tsx、MetaBar.tsx | 官方入口交互、移动布局与展示总数 |
| apps/web/src/components/BookmarkButton.tsx、ResultCard.tsx | 共享收藏逻辑 |
| apps/web/src/App.tsx、types.ts、styles.css | 键盘、类型与入口样式 |
| scripts/verify-official.py | 最终来源与状态分类修正 |
| README.md、docs/决策与接口变更.md、docs/进展与欠账.md | 最终行为、接口和验收边界 |
| 本报告、reports/INDEX.md、reports/assets/official-entry-review/ | 报告、台账、脚本和证据 |

上述若干文件已有 DSH 未提交实现，本轮先读取最新内容再增量修复。既有 breaker.py、engines.py、test_breaker.py、probe-engines.py、test_engine_probe.py、db/cache.py、test_navigation_dedupe.py、DSH 原报告等本轮未编辑。apps/web/dist 为本地构建产物。

## 4 验证与证据

测试临时目录用 `$env:TEMP=Join-Path $PWD 'data/review-temp'; $env:TMP=$env:TEMP`。沙箱内 Windows asyncio socketpair 卡在本机 accept（faulthandler 已定位），两次中断后按权限工具在沙箱外运行离线 TestClient，不作产品失败。隔离服务仅绑定 127.0.0.1、禁付费与 RDAP，使用 stub 模型和 data/official-entry-review 下独立 DB/token/favicon，不接正式书签。

| 命令原文 | 真实结果 |
| --- | --- |
| `python -m pytest apps/api/tests/test_official_review.py -q`（修复前） | 退出 1；20 项中 16 失败/4 通过，复现 ID、摘要、身份与意图问题 |
| `python -m pytest apps/api/tests/test_official.py apps/api/tests/test_official_review.py apps/api/tests/test_navigation_dedupe.py -q` | 首轮修复后 64 项通过，退出 0 |
| `python -m pytest apps/api -q -o addopts= --junitxml=reports/assets/official-entry-review/api-tests.xml` | 最终 **427 passed in 8.37s**，退出 0（原 398 + 新 29） |
| `npm --prefix apps/web run build` | 最终 tsc + Vite，46 modules，JS 268.15 kB/gzip 84.42 kB，退出 0 |
| `node --test scripts/browser-check.test.cjs scripts/engine-query.test.cjs` | 15 pass/0 fail，退出 0 |
| `python reports/assets/official-entry-review/serve-review.py` | 浏览器专用六候选 fixture，18175；最终进程 29204 |
| `python reports/assets/official-entry-review/serve-review.py --smoke` | 原始 fixture，18176；最终进程 33412 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18176` | 最终 16/16，三档 3/6/1、路由/安全/缓存/总结/书签/首页通过，退出 0 |
| `python scripts/ci-smoke.py http://127.0.0.1:18176` | 最终 15/15，退出 0；Python 控制台中文有编码替换，布尔与关键数字可核对 |
| `node reports/assets/official-entry-review/verify-browser.cjs` | Chromium 156.0.8078.4，搜索/总结/收藏 API 未打桩（仅 favicon 回 404）；4 官方+2 普通仅显示一次，总数 6；j/b/Enter 实际收藏/打开；总结 [1] 定位官方 r_1；缓存 ID 一致；内容查询无官方区；390/320px 无溢出；pageerror=[]，退出 0 |
| 旧入口核验 JSON 通过 `scripts/verify-official.py` 的 classify 离线重放 | 112 条，107 ok/5 blocked/0 fail，分类无变化；verifier-replay.json 明确无新网络验证 |
| `git -c core.safecrlf=false diff --check` | 退出 0，无空白错误 |

第一次把浏览器专用品牌样本用于固定冒烟，2 项预期不符（strong/related 为空），没有算成通过；随后单独启动原始 fixture，16/16 与 15/15 均通过。PowerShell 冒烟的 exit 会提前结束同一命令中的后续步骤，Python 冒烟已单独执行并存日志。

证据：[本轮目录](../assets/official-entry-review/)：api-tests.xml、browser.json、desktop.png、mobile.png、smoke-powershell.txt、smoke-python.txt、verifier-replay.json 与两个可重跑的隔离验证脚本。截图已人工检查，入口标题和主机无横向溢出。

日常服务只读命令：`$health=Invoke-RestMethod http://127.0.0.1:8000/api/health; $schema=Invoke-RestMethod http://127.0.0.1:8000/api/openapi.json; [pscustomobject]@{status=$health.status;provider=$health.provider;official=$null -ne $schema.components.schemas.SearchResponse.properties.official;official_id=$null -ne $schema.components.schemas.OfficialLink.properties.id} | ConvertTo-Json -Compress`；退出 0，status=ok/provider=searxng/official=false/official_id=false。

未验证：日常进程重启后的真实查询、112 入口当前可达性与身份出处人工逐条审计、真实 LLM 事实质量、正式 Chrome/Android、托管 CI。没有重跑十三引擎矩阵，不据此抵扣历史欠账。

## 5 关键决策

OFFICIAL-R1～R7 详见决策文件。保留人工品牌表、精确主机、单角色一条、只用上游实际候选及 meta.total 的既有接口含义；本轮修复不会补造链接。路径认证采取保守策略，含编码的合法地址仍可作为普通结果展示。

## 6 遗留与风险

- 8000 日常进程仍是无 official 字段的旧版；本轮源码已验收，部署尚未更新。前端本地 dist 已更新，旧接口仍能被兼容渲染；官方区需新 API 生效后才显示。
- 入口表人工维护与原 5 个 blocked 项继续存在。离线重放只能证明新判断器与旧证据一致，不能充当新一轮身份核验。
- 同角色其他官方路径/语言版本仍按原策略处理；严格导航词规则遇到未列词汇会保留普通结果，可按真实用例补词，不泛化成任意品牌内容置顶。
- 总结仍有最多 10 来源/全文 5 条限制，官方优先不保证每个来源都被模型引用，也不保证模型表述正确。
- 临时服务验收后停止，正式 8000/8888 未重启；隔离数据和证据保留。没有提交/推送或构建新镜像。

## 7 交接

下一步：沿用已核对的正式 DB/token/模型环境更新本机 API，再以真实 deepseek、文档导航与教程查询验收入口、缓存、引用；如要发布按当轮授权执行，勿把隔离库接到日常端口。保留原 M19、Compose、Chrome/Android 等欠账。

本报告完成表示“审查与修复验收完成”，不表示已更新日常服务。入口实现路径和命令均列在 §3/§4；前端截图可用于核对部署后效果。
# 完工报告 · M19 引擎回退复核与边界完善

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261108-1335 |
| 开始 | 2026-11-08 13:35 |
| 结束 | 2026-11-08 13:41 |
| 耗时 | 7 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 完成 |

## 1 任务

**目标**：复核用户指定的 M19 引擎后缀报告与实现，修复可复现边界缺陷，补齐浏览器及真实兜底证据。

**验收标准**：零结果不误回退或熔断；第二页不计费；实例/付费熔断有效；有回退的冷却路线可点；引擎切换不污染查询；脚本按实际来源验收。全套 API、构建、两套冒烟通过，原报告追加差异。

**不做**：不重写 DSH 原报告正文与历史台账行，不覆盖 NAV 去重及 search-v5；不更改排序阈值，不提交/推送，不把尺寸模拟当真机。

报告骨架由 `scripts/new-report.ps1` 于 13:35 生成；前置读台账、决策、DSH 报告、共享交接及部分回归工作早于报告生成时间，表头时间不是本轮第一次操作时间。

## 2 做了什么

1. 先补回退回归，原实现复现 8 项失败；修复正常零结果误计故障/误付费、显式翻页计费、付费冷却绕过、付费合法空态报错。
2. 显式路线遵守实例熔断，同实例故障不重复尝试；可达响应清实例失败串，引擎故障只记引擎；付费兜底失败保留实例错误分类。
3. 目录增加 `can_fallback/selectable`，考虑主源、免费回退、实例和付费冷却；`paid` 尊重总开关及 provider。按钮不挡住可回退路线，搜索结束刷新目录。
4. 引擎按钮从目录读取短码/别名，只替换一个可解析末尾路由，兼容 bang/NFKC，保护 C g 等短基词正文。14 项前端查询回归接入现有 CI 步骤。
5. 保留 NAV 的 search-v5；缓存命名空间补回退策略与全部付费能力，解决双提供商时 Serper 配置变更不失效的问题。
6. 旧探测矩阵发现 4 个来源不匹配的假阳性；修脚本并保留旧证据，新增审计。CSE 提示移除与配置不符的 8 秒描述。
7. 实际 Chromium 验证按钮、健康刷新、查询解析和窄屏；隔离 API 真实验证 Google/Scholar 的 Serper 兜底、缓存冷热及第二页禁付费响应。
8. 原 M19 报告仅追加 §8 更正；README、进度及决策同步，新增证据与独立复核报告。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `apps/api/app/core/aggregator.py`、`paid.py` | 修改 | 显式回退、费用和熔断边界；提供商预检与能力标识 |
| `apps/api/app/core/engine_catalog.py` | 修改 | CSE 提示去掉漂移的超时数字 |
| `apps/api/app/routers/search.py`、`engines.py` | 修改 | 缓存策略隔离、主源与路线可尝试性 |
| `apps/api/tests/test_engine_fallback.py` | 修改 | 9 项新增回归，覆盖费用/零结果/实例恢复与冷却 |
| `apps/api/tests/test_paid.py` | 修改 | 修正原零结果仍付费的错误断言 |
| `apps/api/tests/test_engines_endpoint.py`、`test_cache.py` | 修改 | 总开关、主源/实例/付费冷却和双提供商缓存 |
| `apps/api/tests/test_engine_probe.py` | 新增 | 4 项指定来源、混合来源、空态、坏响应分支 |
| `apps/web/src/App.tsx`、`types.ts`、`components/EngineBar.tsx` | 修改 | 状态刷新、回退可选、只替换路由 |
| `apps/web/src/engineQuery.ts`、`scripts/engine-query.test.cjs` | 新增 | 查询构造及 14 项前端回归 |
| `scripts/probe-engines.py` | 修改 | 指定来源计数，增加 raw_count/routing_ok |
| `.github/workflows/ci.yml` | 修改 | 现有 Node 检查步骤增加引擎查询测试 |
| `README.md`、`docs/决策与接口变更.md`、`docs/进展与欠账.md` | 修改 | M19-R1～R7、接口和验收边界 |
| `reports/2026-11-08-1137-m19-engine-suffix-repair.md` | 追加 | §8 更正，保留原正文与头部 |
| 本报告、`reports/INDEX.md`、`reports/assets/engine-fallback-review/` | 新增/更新 | 复核台账、日志、JUnit、审计、实测和截图 |

上述路径多数已有 M19 未提交改动，本轮基于其最新内容增量修复；其余已有 README、SearXNG 配置、query_parser/searxng/main、前端样式等既有改动均保留。NAV 的 normalize.py、db/cache.py、test_navigation_dedupe.py 未在本轮改写。

## 4 验证与证据

Windows 测试使用工作区临时目录：`$env:TEMP = Join-Path $PWD 'data/review-temp'; $env:TMP = $env:TEMP`。fixture/live 服务的 DB、token、feed、favicon 分别隔离于 `data/engine-review-fixture/` 与 `data/engine-review-live/`，LLM=stub、RDAP=false、CACHE=true。未访问正式书签库。

| 命令原文 | 结果 | 输出摘要 |
| --- | --- | --- |
| `python -m pytest apps/api/tests/test_engine_fallback.py -q`（修复前） | 预期失败 | 8 failed / 5 passed；覆盖零结果误付费、2/3 页付费、429 冷却、付费空态、实例重复失败及恢复 |
| `python -m pytest apps/api/tests/test_engine_fallback.py apps/api/tests/test_paid.py apps/api/tests/test_engines_endpoint.py apps/api/tests/test_engine_probe.py apps/api/tests/test_cache.py -q` | 通过 | 53 项定向回归通过，退出码 0 |
| `python -m pytest apps/api -q -o 'addopts=' --junitxml=reports/assets/engine-fallback-review/api-tests.xml` | 通过 | 362 passed in 8.80s；较原合并工作区 347 项增加 15 项 |
| `node --test scripts/browser-check.test.cjs scripts/engine-query.test.cjs` | 通过 | 15 passed / 0 failed（旧判断器 1 + 引擎查询 14） |
| `npm --prefix apps/web run build` | 通过 | tsc + Vite，44 modules，JS 266.24 kB / gzip 83.83 kB |
| `.\scripts\serve.ps1 -Provider fixture -Port 18172 -SkipBuild` | 通过 | 同源隔离服务启动，进程 39620；用于冒烟和浏览器 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18172` | 通过 | 16/16，搜索/缓存/路由/安全/总结/书签/首页通过 |
| `python scripts/ci-smoke.py http://127.0.0.1:18172` | 通过 | 15/15，退出码 0 |
| `node reports/assets/engine-fallback-review/verify-browser.cjs http://127.0.0.1:18172` | 通过 | 冷却可回退可点、全部冷却禁用、目录刷新 4 次、3 次查询解析正确、无 pageerror；桌面/390px 无横向溢出 |
| `.\scripts\serve.ps1 -Provider searxng -Port 18173 -SkipBuild` | 通过 | 进程 29672；SEARXNG_URL=http://127.0.0.1:1，受控断连；使用已有 Serper 配置 |
| `python reports/assets/engine-fallback-review/verify-live.py` | 通过 | Google 7 条（冷/热 cached=false/true），Scholar 9 条，meta.engines 均 serper；第二页 503 UPSTREAM_UNAVAILABLE |

证据位于 [本轮目录](../assets/engine-fallback-review/)：`api-tests.xml`、`validation.json`、`probe-audit.json`、`smoke-powershell.txt`、`smoke-python.txt`、`browser.json`、`browser-desktop.png`、`browser-mobile.png`、`live-api.json`。验证脚本同目录，可在隔离服务运行时重放；真实接口重放会消耗额度。

浏览器目录为受控响应，查询经真实 fixture API 解析；实际免费/付费回退链由 Mock 契约和两条真实 Serper 查询共同覆盖。第 2 页实际请求未返回付费结果，是否发起计费请求由 Mock 调用计数证明；不单凭 503 推断账单。

未验证：当前 8000/8888 未监听，未运行完整 13 引擎在线矩阵或 Docker 重建；未重跑远端 CI，未做正式 Chrome 手动加载或 Android 真机。本轮不将历史记录算作新结果。PowerShell 的跨平台日志存在控制台编码替换，退出码及 15 个 True 仍可核对；JSON/XML 以 UTF-8 保存。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 正常空态立即成功 | 空结果继续付费/累计故障 | 无命中不等于引擎坏了，避免正常查询耗额度和误熔断 |
| 显式付费只限首屏且预检提供商 | 各路由自行处理费用 | 与既定翻页策略一致，共享配额错误不会被显式入口绕过 |
| 实例失败终止同实例免费候选 | 对每个候选重复请求同一实例 | 降低重复等待与失败计数，保留真实实例错误分类 |
| selectable 与主源 status 分开 | 主源冷却即禁用整条路线 | 可尝试回退不等同主源已恢复；未知也不保证在线 |
| 探测按指定来源验收 | 只看响应总条数 | 防止静默默认聚合制造假阳性；保留原记录以便追溯 |

接口与缓存变更见 [决策 M19-R](../../docs/决策与接口变更.md)。无新环境变量，无评分策略变更。

## 6 遗留与风险

- 原 13 API 后缀记录只证明原时点；直接探测矩阵四行假阳性已追加更正，不改原 JSON。原 M19 报告仍留 reports 根目录，部署复验等原遗留不据此消失。
- `selectable/can_fallback` 反映首屏未冷却路线，不验证 SearXNG 当前安装/启用状态，也不保证未知来源在线；后续页仍严格不付费。
- 两条真实兜底会消耗现有 Serper 额度；报告和产物不保存密钥。Brave 未做真实网络验收，契约覆盖保留。
- CI 增量只在本地通过，未提交/推送，远端结果仍对应上一发布版本。源码需在实际运行进程重启或镜像重建后生效。
- 本轮临时进程结束后核对 18172/18173 不再监听；隔离数据库与证据保留，正式 8000/8888 服务未改动。

## 7 交接

**下一个人第一件事**：在实际使用的部署方式重启 API/重建镜像后，运行更新后的 `scripts/probe-engines.py`，并逐条 POST 13 后缀，核对 parsed.engine、实际 meta.engines、空态、冷却及第 2 页行为；按当轮授权决定发布。

**相关文件**：原报告 §8、[进展与欠账](../../docs/进展与欠账.md)、[聚合器](../../apps/api/app/core/aggregator.py)、[目录接口](../../apps/api/app/routers/engines.py)、[前端查询构造](../../apps/web/src/engineQuery.ts)。

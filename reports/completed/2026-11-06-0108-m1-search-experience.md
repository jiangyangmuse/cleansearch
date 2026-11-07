# 完工报告 · M1 搜索体验：后缀路由与三档分组

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261106-0108 |
| 开始 | 2026-11-06 01:08 |
| 结束 | 2026-11-06 01:09 |
| 耗时 | 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

**目标**

实现首版实施计划 M1：查询后缀 / bang 路由与护栏、URL 规范化去重加强、已知恶意链接拦截、三档相关性分组与结果页渲染。

**验收标准**

- `数分知识点 g` 走 Google；`C g`、`1 g`、`x b`、引号内短码保持普通查询；`天气预报 zh` 单独解析为地区。
- 30–50 条常用查询回归，解析结果逐条断言。
- 已知恶意链接（黑名单命中）直接拦截，不出现在结果里，且计入 `meta.filtered.risk`。
- 全弱结果集不产生强相关条目；强相关允许为空。
- `python -m pytest apps/api` 全绿；`scripts/smoke.ps1` 全通过；浏览器可看到三档分区、路由标记与拦截计数。

**不做**

- 向量语义分（需 bge-m3）、LLM 复核重排（M2 前置）。
- 三源实时黑名单 feed、域名年龄（RDAP）、`/go` 风险中转页（M4）。
- 分页「加载更多」、多页聚合。

## 2 做了什么

1. 新增 `app/core/query_parser.py`：引擎短码（g/b/d/ddg/br/yt/gh/ar/sc/w）、地区短码（zh/cn/jp/us/en）、bang 形式，护栏为「短码前必须有 ≥2 字的真实查询且不是单个 ASCII 字母数字」「引号内 / 未闭合引号不解析」。
2. 新增 `app/core/safety.py`：`Blocklist`（域名与父域匹配 + 完整 URL 精确匹配，按 mtime+size 热加载）与 `SafetyScorer`（可疑 TLD 0.15 / URL 形状 0.10 / 形近字符 0.10，0.35 标记、0.6 拦截）。
3. 新增 `app/core/scoring.py`：词法（BM25 饱和 + 查询词覆盖率）、引擎共识（1/2/≥3 → 0.4/0.8/1.0）、权威域名白名单、时效（仅时间意图）、营销特征负向；绝对分 + 0.55/0.30 阈值分组，容量 10/10/5。
4. `normalize.py` 增加 64 位标题 simhash 与汉明距离近重复合并；`aggregator.py` 在两条上游路径后统一过一遍近重复合并。
5. 打通链路：`routers/search.py` 依次执行 解析 → 聚合 → 安全过滤 → 打分 → 分组；`parsed` 真实返回 `engine/region/router`；`meta` 新增 `upstream_total`；`/api/health` 新增 `blocklist_rules`。
6. 新增 `fixtures/searxng_risky.json` 与 `fixtures/blocklist.txt` 演示样本（`opts.fixture=risky` / 查询前缀 `__risky`）。
7. 前端：三档分区渲染（弱相关 `<details>` 默认折叠）、可疑卡片角标与悬停理由、元信息展示路由与拦截数；自检样本增加「恶意链接」。
8. 测试与脚本：新增 `test_query_parser.py`、`test_safety.py`、`test_scoring.py`、`regression/m1_queries.json`（40 条）；`test_search.py` 补 M1 端到端断言；`smoke.ps1` 扩到 9 项。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| [query_parser.py](../../apps/api/app/core/query_parser.py) | 新增 | 后缀 / bang / 地区解析与护栏 |
| [safety.py](../../apps/api/app/core/safety.py) | 新增 | 黑名单、风险分、热加载 |
| [scoring.py](../../apps/api/app/core/scoring.py) | 新增 | 打分特征、阈值分组、容量上限 |
| [normalize.py](../../apps/api/app/core/normalize.py) | 修改 | 标题 simhash、近重复合并 |
| [aggregator.py](../../apps/api/app/core/aggregator.py) | 修改 | engine 透传、近重复合并 |
| [searxng.py](../../apps/api/app/core/searxng.py) | 修改 | `engines` 参数 |
| [fixture_provider.py](../../apps/api/app/core/fixture_provider.py) | 修改 | risky 样本、engine 参数 |
| [routers/search.py](../../apps/api/app/routers/search.py) | 修改 | 解析 → 过滤 → 打分 → 分组 |
| [schemas.py](../../apps/api/app/schemas.py) | 修改 | `upstream_total`、fixture=risky、health 字段 |
| [config.py](../../apps/api/app/config.py) | 修改 | `BLOCKLIST_PATH` |
| [main.py](../../apps/api/app/main.py) | 修改 | health 返回黑名单条数 |
| [fixtures/searxng_risky.json](../../apps/api/fixtures/searxng_risky.json)、[fixtures/blocklist.txt](../../apps/api/fixtures/blocklist.txt) | 新增 | 恶意 / 可疑链接演示数据 |
| [tests/test_query_parser.py](../../apps/api/tests/test_query_parser.py)、[test_safety.py](../../apps/api/tests/test_safety.py)、[test_scoring.py](../../apps/api/tests/test_scoring.py)、[regression/m1_queries.json](../../apps/api/tests/regression/m1_queries.json) | 新增 | 解析 / 安全 / 打分 / 40 条回归 |
| [tests/test_search.py](../../apps/api/tests/test_search.py) | 修改 | 分档、路由、拦截的端到端断言 |
| [apps/web/src/App.tsx](../../apps/web/src/App.tsx)、[components/ResultList.tsx](../../apps/web/src/components/ResultList.tsx)、[ResultCard.tsx](../../apps/web/src/components/ResultCard.tsx)、[MetaBar.tsx](../../apps/web/src/components/MetaBar.tsx)、[types.ts](../../apps/web/src/types.ts)、[styles.css](../../apps/web/src/styles.css)、[url.ts](../../apps/web/src/url.ts) | 修改 | 三档渲染、折叠、可疑角标、路由信息 |
| [scripts/smoke.ps1](../../scripts/smoke.ps1) | 修改 | 9 项 M1 冒烟 |
| [README.md](../../README.md)、[docs/决策与接口变更.md](../../docs/决策与接口变更.md) | 修改 | M1 说明与 M1-D1…D8 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `python -m pytest apps/api -o addopts= > $env:TEMP\pt2.txt 2>&1; Get-Content $env:TEMP\pt2.txt -Tail 3` | 通过 | `131 passed in 0.40s`；含 40 条解析回归、7 例安全、11 例打分、M1 端到端 |
| `npm --prefix apps/web run build` | 通过 | `tsc --noEmit` 通过，`36 modules transformed` |
| `pwsh -File scripts\smoke.ps1` | 通过 | 9/9，见下 |
| Playwright `check_m1.js`（13 项断言） | 通过 | `ALL PASS` |

冒烟实际输出：

```
health 200   True provider=fixture web_built=True blocklist=3
有结果       True total=10 upstream=10
三档分组     True strong/related/weak=3/6/1
后缀路由     True engine=google router=suffix q=python 文档
C g 不误触发 True router=default
黑名单拦截   True filtered.risk=1 upstream=5
零结果       True total=0
上游不可用   True code=UPSTREAM_UNAVAILABLE
同源首页     True bytes=462
```

浏览器断言（`check_m1.js`）要点：

```
三档分区出现       强相关 3 默认展开 | 相关 6 默认展开 | 弱相关 1 默认折叠
弱相关默认折叠     open=false；展开后可见 1 张
后缀路由展示       后缀路由 · google
黑名单拦截展示     展示 4 条 / 上游 5，拦截 1
被拦截链接未渲染   evil-phish.test 不在 DOM
可疑标记可见       可疑 · 0.35（xn-- 域名卡片）
C g 不显示路由标记 route=absent
移动端无横向溢出   overflow=false
无 JS 运行时错误   ok
```

证据文件：`docs/m1-evidence/01-三档分组.png`、`02-后缀路由.png`、`03-拦截与可疑.png`、`04-移动端.png`。

未验证：真实 SearXNG 上与引擎路由（`engines=google`）的实际效果；本机无 Docker，需部署环境复验。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 绝对分 + 0.55/0.30 阈值，不做 minmax | 沿用构建方案 0.62/0.35 + minmax | minmax 会把垃圾集的最大值拉成 1.0，强相关栏永远有内容，与「强相关允许为空」矛盾 |
| 去掉语义分，权重给词法与共识 | 用本地小模型伪造语义分 | 没有 embedding 就编一个语义分会污染排序；宁可少一个特征也不伪造 |
| 词法 = BM25 饱和 + 覆盖率各半 | 纯 BM25 | 小候选集上 BM25 绝对值偏低，"沾边"和"命中"分不开 |
| 黑名单 URL 规则只做精确匹配，不扩到域名 | 完整 URL 也按域名拦截 | 否则一条 URL 规则会误封整站，反而制造可用性事故 |
| 风险分不接 RDAP / feed | M1 就联网查域名年龄 | 首屏会因外部服务抖动而变慢；且无 key 不可测 |
| 弱相关最多 5 条并默认折叠 | 全部展示 | 熵增会让弱相关变垃圾场，且与设计文档一致 |

## 6 遗留与风险

- 没有向量语义分，同义改写召回弱（"数分" vs "数据分析"），M7 或接入 bge-m3 后需重新标定阈值。
- 阈值 0.55/0.30 来自固定样本 + 40 条查询的手工标定，样本量小，真实流量下大概率还要调；调整前先改回归集期望值再改常量。
- 权威域名白名单硬编码在 `scoring.py`，新增站点要改代码；建议 M4 外置为 JSON 配置。
- 三档容量截断（10/10/5）没有「加载更多」，结果多的查询会少展示。
- 黑名单规则未做入库与去重，规则上万条时应改用 SQLite 或前缀树。
- 真实 SearXNG 的引擎路由参数（`engines=`）未在真实实例上验证过。

## 7 交接

**下一个人第一件事**

在部署机跑 `SEARCH_PROVIDER=searxng docker compose up -d`，用 `curl -X POST http://127.0.0.1:8000/api/search -H "Content-Type: application/json" -d '{"q":"数分知识点 g"}'` 确认 `parsed.engine=google` 且上游确实只回了 Google 结果。

**相关文件**

- [首版实施计划](../../docs/搜索聚合器-首版实施计划.md)
- [M1 决策 M1-D1…D8](../../docs/决策与接口变更.md)
- [解析器](../../apps/api/app/core/query_parser.py)、[打分](../../apps/api/app/core/scoring.py)、[安全过滤](../../apps/api/app/core/safety.py)
- [M1 截图](../../docs/m1-evidence)

---

> 注：头部「耗时」由 `close-report.ps1` 按报告起草时间计算；本轮从读决策文档到验收完成实际约 45 分钟。

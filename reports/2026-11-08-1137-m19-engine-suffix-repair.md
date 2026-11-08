# 完工报告 · M19 引擎后缀可用性修复

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261108-1137 |
| 开始 | 2026-11-08 11:37 |
| 结束 | 2026-11-08 11:39 |
| 耗时 | 2 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | fix |
| 状态 | 完成 |

> 注：耗时由 `close-report.ps1` 按报告起草时间计算；本轮实际约 25 分钟（含逐引擎探测、真实 API 复测与前端构建）。

## 1 任务

**目标**

修复「大部分引擎后缀不可用」：让显式后缀在真实 SearXNG 上尽量有结果，失败时按回退链接管；同时给前端一个可见的引擎目录与状态入口。

**验收标准**

- 至少 10 个后缀经真实 `POST /api/search` 请求返回 `meta.total > 0`，包括此前失败的 `b`、`w`、`g`、`sc`、`sg`、`sp`。
- `g` 在 Google 直连 403 后能通过 Google CSE 或 Serper 返回结果；`sc` 在 Scholar 被拒后能通过 Serper `/scholar` 返回结果。
- `GET /api/engines` 返回目录、回退链和健康状态；前端构建通过。
- `python -m pytest apps/api -q -o "addopts="` 全绿；`scripts/smoke.ps1` 16/16。
- SearXNG 配置能解释每个修复点：`bing` 的 `cn.bing.com`、`wikipedia` 的 list、`mojeek/swisscows` 的 `inactive: false`。

**不做**

- 不改默认排序、风险权重、总结提示词；不保证第三方引擎永久可用。
- 不修改 SearXNG 上游源码，不把网页端被封锁的 Google/Scholar 伪装成可用。
- 不执行 `git commit` / `git push`。
- 不动工作区里他人进行中的 `normalize.py`、`db/cache.py`、`test_navigation_dedupe.py`、`reports/assets/navigation-search/`。

## 2 做了什么

1. **定位根因**：SearXNG 的 `disabled` 与 `inactive` 是两层开关，`mojeek/startpage/swisscows/dogpile` 默认 `inactive: true`，只写 `disabled: false` 不会加载；`www.bing.com` 会 302 到 `cn.bing.com`，而引擎请求默认不跟随重定向；`wikipedia` 默认只返回 infobox，后缀需要 list；Google/Scholar 在本机 IP 被 403；Sogou 在 SearXNG 侧 crash；Startpage 走 PoW CAPTCHA。
2. **修 SearXNG 配置**：`searxng/settings.yml` 启用 `bing`（`base_url: https://cn.bing.com`）、`mojeek`、`swisscows`、`360search`、`naver`、`yandex`、`duckduckgo web`；给 `wikipedia` 补 `display_type: [infobox, list]`；给 `arxiv/github/youtube/google cse` 单独放宽超时；Google/Scholar/Brave/Startpage 保持禁用，避免拖慢默认聚合。
3. **收敛引擎目录**：新增 `app/core/engine_catalog.py`，把后缀、SearXNG 引擎名、回退链、付费路由集中到一处；`query_parser` 继续导出 `ENGINE_SUFFIXES`。
4. **聚合器回退**：显式引擎失败时按 `engine_candidates()` 依次尝试（`g → google cse`、`sg → 360search`、`sp → mojeek`、`d → duckduckgo web`），全部失败后才调用 Serper；默认聚合与翻页的付费策略保持不变。
5. **接口与前端**：新增 `GET /api/engines`；首页增加引擎按钮、可用状态点和「更多」展开；点击后缀自动去掉末尾旧短码再追加，避免 `python 文档 g b`。
6. **证据与文档**：真实 API 13 个后缀矩阵、SearXNG 逐引擎矩阵、`/api/engines` 快照；补测试、README 引擎表、M19 决策、进展页链接。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `apps/api/app/core/engine_catalog.py` | 新增 | 后缀/引擎名/回退链/付费路由单一真源 |
| `apps/api/app/core/aggregator.py` | 修改 | 显式引擎回退链与定向付费兜底 |
| `apps/api/app/core/paid.py` | 修改 | `search_for_engine` 与 Serper `/scholar` |
| `apps/api/app/core/query_parser.py` | 修改 | 后缀表改由 catalog 生成 |
| `apps/api/app/core/searxng.py` | 修改 | 使用 catalog 的 SearXNG 引擎名 |
| `apps/api/app/routers/engines.py` | 新增 | `GET /api/engines` |
| `apps/api/app/main.py` | 修改 | 挂载 engines 路由 |
| `apps/api/tests/test_engine_catalog.py` | 新增 | 后缀、回退链、付费路由 |
| `apps/api/tests/test_engine_fallback.py` | 新增 | 回退、零结果、全失败 |
| `apps/api/tests/test_engines_endpoint.py` | 新增 | `/api/engines` 契约 |
| `apps/api/tests/test_paid.py` | 修改 | 显式引擎允许付费兜底；新增 Scholar 路由用例 |
| `apps/web/src/components/EngineBar.tsx` | 新增 | 首页引擎按钮与状态点 |
| `apps/web/src/App.tsx`、`api.ts`、`styles.css`、`types.ts` | 修改 | 拉取 `/api/engines`、点击后缀、样式与类型 |
| `scripts/probe-engines.py` | 新增 | SearXNG 逐引擎探测脚本 |
| `searxng/settings.yml` | 修改 | 引擎启用、`cn.bing.com`、超时、wikipedia list |
| `README.md` | 修改 | 引擎表、API 端点、回退规则 |
| `docs/决策与接口变更.md` | 修改 | M19-D1…D6 |
| `docs/进展与欠账.md` | 修改 | 当前进度与 P0 行 |
| `reports/assets/m19-engines/` | 新增 | 引擎矩阵、API 验证、`/api/engines` 快照 |

仓库外同步：`D:\agent\build\searxng-settings.yml`（本机源码形态实际读取的配置）按同样内容更新。工作区里 `apps/api/app/core/normalize.py`、`apps/api/app/db/cache.py`、`apps/api/tests/test_navigation_dedupe.py`、`reports/assets/navigation-search/` 的改动不是本轮产生的，未做修改。

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `python -m pytest apps/api -q -o "addopts="` | 通过 | **347 passed in 9.10s** |
| `npm --prefix apps/web run build` | 通过 | tsc + vite，**43 modules transformed** |
| `pwsh -File scripts/smoke.ps1 -BaseUrl http://127.0.0.1:8001` | 通过 | fixture + stub 总结，**16/16** |
| `python scripts/probe-engines.py --base-url http://127.0.0.1:8888` | 部分可用（符合预期） | 见下表；不可用引擎用于回退验证 |
| 真实 `POST /api/search` 13 个后缀 | 通过 | 13/13 `total > 0`，见 [api-engine-verify.json](assets/m19-engines/api-engine-verify.json) |
| `GET /api/engines` | 通过 | 200；19 个目录项，`paid.serper=true`，见 [engines.json](assets/m19-engines/engines.json) |
| 默认聚合查询（无后缀） | 通过（有 1 次瞬时超时） | 重试两次：4.6s/5.7s，17–18 条，来源 10 个 SearXNG 引擎 + serper |

SearXNG 逐引擎矩阵（2026-11-08，源码实例 :8888，每引擎两轮）：

```
bing 10/10 · duckduckgo 10/10 · duckduckgo web 10/10 · yahoo 7/7 · google cse 20/20
mojeek 10/10 · naver 19/14 · swisscows 20/9 · yandex 10/15 · 360search 4/6
youtube 15/17 · github 30/30 · arxiv 10/10
google 0/0（access denied） · google scholar 0/0（access denied）
sogou 0/0（SearXNG crash） · startpage 0/0（CAPTCHA） · brave 0/0（限流）
```

真实 API 后缀矩阵（`POST /api/search`，本机 :8000，真实 SearXNG + Serper）：

| 后缀 | total | 实际来源 | 失败尝试 |
| --- | --- | --- | --- |
| `b` | 10 | bing | — |
| `d` | 10 | duckduckgo | — |
| `y` | 7 | yahoo | — |
| `mj` | 10 | mojeek | — |
| `gc` | 13 | google cse | — |
| `n` | 16 | naver | — |
| `yd` | 10 | yandex | — |
| `sw` | 10 | swisscows | — |
| `w` | 1 | wikipedia | — |
| `g` | 12 | google cse | google(access denied) |
| `sc` | 10 | serper | google scholar(access denied) |
| `sg` | 5 | 360search | sogou(crash) |
| `sp` | 10 | mojeek | startpage(路由未生效) |

证据文件：

- [SearXNG 引擎矩阵](assets/m19-engines/engine-probe.json)
- [API 后缀矩阵](assets/m19-engines/api-engine-verify.json)
- [GET /api/engines 快照](assets/m19-engines/engines.json)

未验证：

- 正式浏览器里点引擎按钮的视觉验收：只做了 `tsc + vite` 构建和接口检查，没有截图。
- Docker Compose 形态：本机 Docker Desktop 已安装但守护进程未启动，未重建容器。
- `br` 的官方 API 兜底：没有 `BRAVE_API_KEY`，只验证了无 key 时不会误调付费接口。
- 默认查询的首个请求曾出现一次 11s `UPSTREAM_TIMEOUT`（随后回退 Serper 成功），重试两次正常；未归因为冷启动或代理抖动。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 后缀表放 `engine_catalog.py` 单一真源 | 继续在 `query_parser` 手写、在 `/api/engines` 再抄一份 | 三处表迟早漂移；catalog 同时给解析、回退、前端状态用 |
| 显式引擎按回退链继续 | 直接 503 让用户换后缀 | 用户输入的语义是「用 Google/学术/搜狗」，同语义的 CSE/Serper/360 比报错更有用 |
| `g` 付费兜底只在 CSE 也失败后触发 | 一开始就调 Serper | 控制额度；`gc` 实测 0.6s 能出 13–20 条，优先免费路径 |
| `bing` 用 `cn.bing.com` | 改 SearXNG 源码让引擎跟随 302 | 配置层能解决，不动上游；301/302 默认不跟随是 SearXNG 引擎层的既有行为 |
| 零结果返回空态 | 一律 `ENGINE_UNAVAILABLE` | 引擎正常但没有匹配，和引擎未启用是两件事；前端应显示“无结果” |
| `/api/engines` 暴露状态 | 只写死在数据库/日志里 | 用户需要知道哪个后缀现在能用，前端按钮才有意义 |

## 6 遗留与风险

- `google`、`google scholar`、`brave`、`startpage` 网页端仍被目标站拒绝/限流；`g/sc` 依赖 `SERPER_API_KEY`，`br` 依赖 `BRAVE_API_KEY`。
- Serper 兜底会消耗额度；本次验证实际调用了 `/search` 与 `/scholar` 少量请求。未配置 key 时 `g` 只剩 Google CSE，`sc` 会返回 `ENGINE_UNAVAILABLE`。
- 默认聚合包含 10 个 SearXNG 引擎，正常 4–6s；首个请求出现过一次 11s 超时。若线上频繁出现，考虑提高 `SEARCH_TIMEOUT` 或预热 SearXNG。
- `w` 的 Wikipedia 只对存在词条的查询有结果；冷门多词查询会显示空态。
- SearXNG 的 `inactive: true` 引擎在显式请求时会静默回落默认集；应用层靠「过滤后无结果」判失败。以后新增引擎必须同时检查 `disabled` 和 `inactive`。
- Docker Compose 镜像里的 SearXNG 版本可能与本机源码实例不同；`searxng/settings.yml` 已同步，但容器形态未重建验证。
- 前端只做了构建验证，没有在真实浏览器里截图；`/api/engines` 不可用时按钮会隐藏，搜索仍可用。

## 7 交接

**下一个人第一件事**

有 Docker 时执行 `docker compose up -d --build`，然后 `curl http://127.0.0.1:8888/search?q=python&format=json&engines=bing` 与 `curl http://127.0.0.1:8000/api/engines`，确认容器内 `bing/mojeek/swisscows` 与宿主一致；若某个后缀仍失败，先跑 `python scripts/probe-engines.py --base-url http://127.0.0.1:8888 --engines <name>` 定位是配置、封锁还是解析问题。

**相关文件**

- [引擎目录](../apps/api/app/core/engine_catalog.py)
- [聚合器回退](../apps/api/app/core/aggregator.py)
- [SearXNG 配置](../searxng/settings.yml)
- [引擎探测脚本](../scripts/probe-engines.py)
- [M19 决策](../docs/决策与接口变更.md)
- [证据目录](assets/m19-engines/)

## 8 追加轮次 2026-11-08 · Codex 复核更正

本节保留原报告正文、结束时间和历史状态，补充用户指定的独立复核结论。详细实现、命令与证据见 [复核报告](completed/2026-11-08-1335-engine-fallback-review.md)。

### 发现与修正

- 原“默认聚合与翻页付费策略不变”存在实现偏差：显式引擎第 2 页仍可调用付费源，且未预检提供商冷却。现限第 1 页，并遵守匹配提供商熔断；失败每次只计一次。
- 原“零结果不算故障”只体现在最终响应：内部仍累计 empty 故障，并可能继续回退付费。现免费或付费合法零结果立即返回空态，不因零命中熔断。
- 原显式路线未检查实例熔断，同实例断连会按候选重复等待，成功又未清实例失败串。现遵守实例冷却，一次实例故障中止免费链；引擎级失败单独计数，恢复可清实例失败串，保留实例错误码。
- 主源冷却时前端原先一律禁用按钮，挡住了 CSE/Serper 等回退。现目录增加 `can_fallback/selectable`，按钮考虑回退来源，查询后刷新状态；`paid` 尊重总开关，未知状态不代表已实测可用。
- 原按钮只剥裸后缀且循环删除，切换 `python !g` 会残留旧 bang，`C g` 等正文也可能被删。现只替换一个实际可解析的路由；短码/别名来自目录，不再手抄引擎正则。
- 缓存命名空间加入回退策略与全部付费能力，避免双 key 时切换 Serper 仍复用缓存；保留 NAV 的 `search-v5`。
- 原 `engine-probe.json` 的 **startpage / marginalia / dogpile / yandex api** 虽 `ok=2`，`sources` 均不含请求引擎，是默认聚合假阳性。旧证据保留，新增 [审计](assets/engine-fallback-review/probe-audit.json)；探测脚本改为按实际来源统计。原 API 13 后缀记录为另一层证据，`sp` 本来即标为 Mojeek 回退，不据此宣称 Startpage 直连可用。
- CSE 目录提示中的“8s”与配置的 6 秒不一致，已去掉易漂移的硬编码耗时描述。

### 新增验收与边界

- 新回退回归在原实现上 **8 失败 / 5 通过**，修复后通过；全套 `python -m pytest apps/api -q -o 'addopts='` 为 **362 passed in 8.80s**，较原 347 项新增 15 项。
- `node --test scripts/browser-check.test.cjs scripts/engine-query.test.cjs` **15/15**；`npm --prefix apps/web run build` **44 modules**。新增前端回归已接入 CI 配置，未运行新远端 CI。
- `scripts/smoke.ps1` 在隔离 fixture 18172 **16/16**；`scripts/ci-smoke.py` **15/15**。总结使用 stub，不触碰本机模型及正式书签库。
- Chromium 实际按钮检查：有回退的冷却主源可点、全部冷却后禁用、搜索后刷新、bang 切换与 `C g` 正文保护通过；1280×900 与 390×844 截图及无横向溢出证据见 `assets/engine-fallback-review/`。目录受控、查询解析走真实 fixture API；不等同 Android 真机或正式 Chrome 手动验收。
- 隔离 API 受控断开 SearXNG 后，真实 Serper Google/Scholar 兜底返回 **7/9** 条；Google 重复查询缓存命中，第 2 页 **503 UPSTREAM_UNAVAILABLE**，禁付费计数另由 Mock 回归证明。来源及响应摘要见 [实测](assets/engine-fallback-review/live-api.json)。
- 本轮未运行完整 13 引擎在线矩阵或 Docker 重建；原记录仅证明原时点结果。部署复验继续沿用 §7，须使用更新后的探测脚本核对指定来源。未执行提交/推送。

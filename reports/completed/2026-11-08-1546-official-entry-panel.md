# 完工报告 · 品牌入口表与独立官方入口区

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261108-1546 |
| 开始 | 2026-11-08 15:46 |
| 结束 | 2026-11-08 15:46 |
| 耗时 | 不到 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

**目标**

落地可维护的品牌入口表，并在搜索首屏新增独立「官方入口」区，按精确主机 + 路径 + 核验来源识别官网、聊天、文档、控制台等入口；未知品牌保持普通结果，自称「官网」的页面不被误标。

**验收标准**

- 品牌导航查询返回 `official` 分区，条目按角色排序，URL 来自上游实际返回的候选；
- 伪装域名（`www.deepseek.com.example.org`）、缺 `www` 的近似域、共享托管上的其他组织不被识别；
- 教程 / 新闻 / 对比 / 招聘类查询与未知品牌不产生官方入口区；
- 同地址不在官方入口区和三档列表里重复出现，`meta.total` 与实际卡片数一致，缓存命中后分区不变；
- `python -m pytest apps/api -q`、前端构建、固定样本冒烟通过；入口表逐条可核验。

**不做**

- 不改打分权重、三档阈值与排序公式；不整域认证共享托管域名；
- 不推造上游未返回的链接；不提交 / 推送；不改动其他执行体正在修改的 breaker、engines、probe 等文件。

## 2 做了什么

1. 新增入口表 `apps/api/app/core/official.py`：46 个品牌、112 条入口，每条记录角色、精确主机、允许路径、核验来源与日期；查询侧按完整词元匹配别名，教程 / 新闻 / 对比 / 招聘意图直接放弃分区。
2. 结果侧匹配只认精确主机与路径语义：`/` 只认首页与语言首页，其他路径按目录边界前缀（`/docs` 不匹配 `/docsomething`），共享托管必须带组织前缀（`github.com/python`）；同角色只取一条，表格顺序即优先级。
3. 搜索主链路在打分后、三档截断前提取官方入口，把它从 `groups` 移除并单独返回 `official`；命中缓存时从载荷还原分区，快照登记官方入口供总结引用。
4. 响应模型新增 `OfficialLink` / `OfficialSection` 与 `meta.official`；缓存命名空间加入 `official-v1`、键版本升到 `search-v6`，避免旧缓存继续展示重复入口。
5. 前端新增 `OfficialPanel`：品牌名、角色标签、标题、精确主机与核验日期，悬停显示核验来源；`MetaBar` 显示入口条数；只有官方入口、没有三档结果时仍按 `ok` 渲染。
6. 新增 `scripts/verify-official.py`：并发请求每条入口，按 ok / blocked / fail 分类，写资产 `reports/assets/official-entries/verified.json`。
7. 按核验结果修正入口表：Claude 控制台与文档迁到 `platform.claude.com`、OpenAI 文档迁到 `developers.openai.com`、Kimi 迁到 `www.kimi.com`/`platform.kimi.com`、文心迁到 `wenxin.baidu.com`、千问迁到 `qianwen.aliyun.com`；删除未能核验的 Meta 品牌与 Copilot 聊天入口、Vercel 不存在的 dashboard 路径。
8. 同步 `docs/决策与接口变更.md`（OFFICIAL-D1～D7）与 README 的官方入口、接口契约、目录结构段落。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `apps/api/app/core/official.py` | 新增 | 品牌入口表、别名识别、路径语义、入口提取 |
| `apps/api/app/schemas.py` | 修改 | `OfficialLink`、`OfficialSection`、`meta.official`、`SearchResponse.official` |
| `apps/api/app/routers/search.py` | 修改 | 提取顺序、分区返回、缓存读写、快照登记 |
| `apps/api/app/db/cache.py` | 修改 | 搜索缓存键版本 `search-v6` |
| `apps/api/tests/test_official.py` | 新增 | 33 项：表格约束、别名、意图、路径、伪装域、共享托管、分区、缓存 |
| `apps/api/tests/test_navigation_dedupe.py` | 修改 | 品牌导航契约改为：首页/聊天进入 `official`，三档只剩参考页，去重引擎仍合并 |
| `apps/web/src/components/OfficialPanel.tsx` | 新增 | 独立官方入口区组件 |
| `apps/web/src/types.ts` | 修改 | `OfficialLink` / `OfficialSection` / `meta.official` |
| `apps/web/src/App.tsx` | 修改 | 渲染入口区、`ok` 判定、首页说明 |
| `apps/web/src/components/MetaBar.tsx` | 修改 | 展示官方入口条数 |
| `apps/web/src/styles.css` | 修改 | 官方入口区样式 |
| `scripts/verify-official.py` | 新增 | 入口表核验脚本 |
| `docs/决策与接口变更.md` | 修改 | OFFICIAL-D1～D7 与接口增量 |
| `README.md` | 修改 | 官方入口章节、API 契约、目录结构 |
| `reports/assets/official-entries/verified.json` | 新增 | 112 条核验明细 |
| `reports/assets/official-entries/official-section.png` | 新增 | 真实查询下的界面截图 |

工作区里 `breaker.py`、`engines.py`、`probe-engines.py`、`docs/进展与欠账.md` 等改动来自其他执行体，本轮未触碰；`data/navigation-isolated-review/` 为既有隔离副本，未读取也未修改。

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `python -m pytest apps/api -o addopts='' -q` | 通过 | `398 passed in 8.64s`（含新增 33 项官方入口用例，原基线 365） |
| `npm --prefix apps/web run build` | 通过 | `tsc --noEmit` + vite build，45 modules，退出码 0 |
| `python scripts/verify-official.py --workers 6 --timeout 20` | 通过（含受限项） | 通过 107 / 受限 5 / 失败 0，共 112；受限为 Cloudflare 反爬 403：claude.ai、dash.cloudflare.com、www.npmjs.com、openai.com、platform.openai.com |
| `& './scripts/smoke.ps1' -BaseUrl http://127.0.0.1:8101`（临时 fixture 实例） | 通过 | 16/16：三态、路由、拦截、缓存、引用、书签、同源首页 |
| 隔离实例 `POST /api/search {"q":"deepseek"}`（searxng，临时端口 8100） | 通过 | `official.key=deepseek`，4 条（home/chat/docs/console），`meta.official=4`、`total=17`；这四个 URL 不在 groups 中 |
| 无头 Chrome 截图 `http://127.0.0.1:8100/?q=deepseek` | 通过 | `official-section.png` 1280×1400，可见「官方入口 · DEEPSEEK」与 4 个角色胶囊，MetaBar 显示「官方入口 4」 |

对应真实响应片段（截断）：

```json
{"official":{"key":"deepseek","brand":"DeepSeek","entries":[
  {"role":"home","label":"官网","url":"https://www.deepseek.com/","host":"www.deepseek.com","verified":"2026-11-08"},
  {"role":"chat","label":"聊天","url":"https://chat.deepseek.com/","host":"chat.deepseek.com","verified":"2026-11-08"},
  {"role":"docs","label":"API 文档","url":"https://api-docs.deepseek.com/","host":"api-docs.deepseek.com","verified":"2026-11-08"},
  {"role":"console","label":"开放平台","url":"https://platform.deepseek.com/","host":"platform.deepseek.com","verified":"2026-11-08"}]},
 "meta":{"total":17,"official":4,...}}
```

负例由 `test_official.py` 固定：`www.deepseek.com.example.org`、`deepseek.com`、`chat.deepseek.com.login.example.net`、`github.com/other-org`、`platform.openai.com/docsomething`、未知品牌、教程/新闻/招聘查询均不进入分区。

未验证：

- 线上 8000 实例仍是本轮之前的旧进程（`GET /api/health` 正常，但运行版无 `official` 字段）。新代码只在隔离端口 8100/8101 验过；按 `.scriptsserve.ps1` 重启后才会对日常使用生效。本轮未擅自重启用户正在用的服务。
- 直接对 8000 跑 `smoke.ps1` 有 4 项失败（黑名单域名、`__empty`/`__fail`、本地总结桩），原因是该实例为 searxng 模式、脚本期望固定样本；换 fixture 实例后 16/16 通过，非回归。
- 无头截图不等于正式浏览器手动验收；移动端布局未单独截图。
- 总结引用只确认快照登记了官方入口，没有逐条断言 cite 文案。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 入口表作为官方身份唯一真源 | 按标题含「官网」、docs 前缀或模型判断 | 三种启发式都能被仿站利用；表可审计、可复核、可回归 |
| 只认精确主机 + 路径，共享托管带组织前缀 | 允许 `*.brand.com` 通配、或整域认证 github.com | 通配会把仿站子域一起放进来；整域认证会把他人仓库标成官方 |
| 官方入口独立分区并从三档移除 | 保留在三档里再加角标 | 重复展示会让「展示 N 条」与卡片数不一致，也与「集中展示」目标冲突 |
| 教程/新闻/对比/招聘查询不显示分区 | 只要出现品牌词就置顶全部入口 | 内容型查询的主体是答案而非导航，置顶会挤掉真正结果 |
| 核验分 ok/blocked/fail | 只有 200 才算通过、其余删表 | 403 是反爬而不是域名写错；一刀切会误删官方站点，也会把真实的 404 掩盖掉 |

## 6 遗留与风险

- 5 条受限入口（Claude、Cloudflare、npm、OpenAI 官网/控制台）只证明了反爬存在，没用响应确认身份；换网络或带浏览器 UA 复核后再决定是否保留。
- 入口表人工维护：新品牌、路径改版、地区跳转都要改表并重跑 `verify-official.py`；表只说明身份，不代表页面长期可用。
- 未收录的官方路径（如 `www.deepseek.com/en/platform/`、`download.deepseek.com`）仍按普通结果展示；要进分区得先补表并重跑核验。
- 同一角色的语言版本只保留一条；多官方站点同角色（如双文档域名）会被表格顺序吞掉，需要时改成多角色或多条策略。
- 线上 8000 尚未重启，新接口未对日常使用生效；重启后需复跑一次真实查询与冒烟。
- 未提交 / 推送；工作区仍有其他执行体的并发改动。

## 7 交接

**下一个人第一件事**

重启本机服务（`.scriptsserve.ps1`，searxng 模式）后打开 `http://127.0.0.1:8000/?q=deepseek`，确认「官方入口」区出现且与三档结果无重复；再跑 `python scripts/verify-official.py` 复核 5 条受限入口。

**相关文件**

- `apps/api/app/core/official.py`、`apps/api/tests/test_official.py`
- `apps/api/app/routers/search.py`、`apps/api/app/schemas.py`
- `apps/web/src/components/OfficialPanel.tsx`、`apps/web/src/App.tsx`
- `scripts/verify-official.py`、`reports/assets/official-entries/`
- `docs/决策与接口变更.md`（OFFICIAL-D1～D7）

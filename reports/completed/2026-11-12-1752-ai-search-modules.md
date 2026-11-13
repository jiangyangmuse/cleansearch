# 完工报告 · DeepSeek 检索开关、游戏官网与内容模块

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261112-1752 |
| 开始 | 2026-11-12 17:52 |
| 结束 | 2026-11-12 18:00 |
| 耗时 | 8 分钟 |
| 执行者 | Codex |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

接入 DeepSeek 网页检索与右侧结果栏。支持末尾 ds 和日常开关，补齐明日方舟与 Nexon 官网，并按百科、应用下载、视频展示命中内容。验收覆盖真实 API、浏览器交互、官网导航及原有搜索回归。

上轮已恢复原生 8000 与 Docker SearXNG 检索链。按台账核对真实模式和固定样本冒烟的差异后继续实施。

## 2 做了什么

- 增加 DeepSeek Search API 适配器和 `POST /api/ai-search`。搜索栏并行提交普通搜索与 AI 请求，右栏各自显示加载、结果、空态或失败。使用本地密钥文件或环境变量，按查询缓存已取得的结构化结果。
- 支持 `ds` / `!ds` 单次启用。日常开关默认关，浏览器保存选择。打开后随新查询调用 AI，关闭时可继续用后缀。翻页沿用当前 AI 栏。
- 核验明日方舟大陆官网和 Nexon 全球及韩国官网入口，补到既有导航目录。搜索命中时展示候选，漏召回时提供目录直达。
- 依据落地页主机与路径对结果标记百科、应用下载、视频。主区和 AI 区各自使用模块展示，键盘选择包含模块结果，已有引用 ID 可继续定位原卡片。
- 备份本机数据库与令牌后更新日常服务，原生 PID 从 18032 切换到 33148。

## 3 改动清单

| 路径 | 内容 |
| --- | --- |
| `apps/api/app/core/ai_search.py`、`routers/search.py` | DeepSeek 适配、独立端点、缓存与本地链接安全处理 |
| `apps/api/app/core/result_category.py`、`normalize.py`、`schemas.py` | 落地页类别与响应字段 |
| `apps/api/app/core/official.py`、`query_parser.py` | 官网入口和 ds 解析 |
| `apps/web/src/App.tsx`、`api.ts`、`engineQuery.ts`、`types.ts`、`styles.css` | 开关、请求生命周期、布局及键盘选择 |
| `apps/web/src/components/AISearchPanel.tsx`、`ContentModules.tsx` | AI 检索栏和三个分类模块 |
| `apps/api/tests/test_ai_search.py`、`scripts/engine-query.test.cjs` | 新接口、失败隔离、分类和后缀回归 |
| `.env.example`、`README.md`、`docs/决策与接口变更.md` | 密钥配置、使用方法及新增接口约定 |
| `reports/assets/ai-search-modules/` | 真实 API 结果、浏览器截图和验证脚本、重启核对记录 |

## 4 验证与证据

| 命令或请求 | 真实结果 |
| --- | --- |
| `python -m pytest apps/api -q -o addopts= --tb=short` | 447 passed in 8.64s，退出 0 |
| `node --test scripts/engine-query.test.cjs` | 16 passed，退出 0 |
| `npm --prefix apps/web run build` | tsc 与 Vite 通过，48 模块，退出 0 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18180` | 最终固定样本 16/16，空态、黑名单、故障及引用均通过 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18179` | 隔离真实模式冒烟通过，固定样本专用三项记 N/A |
| `POST http://127.0.0.1:18179/api/ai-search`，q 为明日方舟 ds | 真实 DeepSeek HTTP 200，返回 10 个网页。改用 !ds 重复查找时 cached=true |
| `node reports/assets/ai-search-modules/verify-browser.cjs` | 浏览器默认关、后缀启动、日常开、刷新保留、关闭、翻页、桌面右栏和 390px 无横向溢出均通过。三分类各一条的页面回放通过 |
| `python reports/assets/ai-search-modules/restart-native.py` | 健康为 ok，OpenAPI 有新端点及类别字段。数据库、令牌、运行配置及 SearXNG 进程核对一致 |
| `POST http://127.0.0.1:8000/api/search`，q 为明日方舟 !b 和 nexon !b | 两次实际来源均为 bing，分别显示明日方舟真实官网候选及 Nexon 全球官网目录直达 |
| `git -c core.safecrlf=false diff --check` | 无空白错误 |

实测记录在 [live-api.json](../assets/ai-search-modules/live-api.json)、[daily-api.json](../assets/ai-search-modules/daily-api.json)、[browser.json](../assets/ai-search-modules/browser.json) 和 [restart.json](../assets/ai-search-modules/restart.json)。截图分别为 [桌面](../assets/ai-search-modules/desktop.png) 和 [窄屏](../assets/ai-search-modules/mobile.png)。浏览器重用隔离库中已取得的 DeepSeek 响应，避免重复消耗 API 额度。三分类的定向验证使用已知类型回放，真实 DeepSeek 首批样本命中百科和应用下载。

## 5 关键决策

- 使用原生网页检索 API。它直接提供 URL、标题及摘要，适配层提供通用结果接口，后续服务商可实现同一接口。
- 日常开关为浏览器偏好。原有总结和本次网页检索各有调用路径。
- 类别模块按候选类型出现。官网目录和页面类别使用既有安全过滤与结果标识。

资料见 [DeepSeek Search API](https://api-docs.deepseek.com/guides/search/)、[明日方舟大陆官网](https://ak.hypergryph.com/)、[Nexon 全球官网](https://www.nexon.com/main/en)。

## 6 遗留与风险

- 结果分类覆盖已识别的网站和 URL 类型，实际每次出现的模块取决于上游候选。视频类别的可视验证使用回放样本。
- DeepSeek 的成功查询按其接口规则计费，日常模式的开关由浏览器保存。更换其他 API 需要补相应适配器。
- 实时检索由 18179 完成，日常 8000 验证了新接口加载及 Bing 官网导航。没有为 8000 再提交一次付费样本。

## 7 交接

打开日常 8000 页面搜索“明日方舟 ds”，右栏显示 AI 检索。需要日常自动检索时打开搜索框下方开关。验证实例 18179、18180 已结束，日常服务继续运行。
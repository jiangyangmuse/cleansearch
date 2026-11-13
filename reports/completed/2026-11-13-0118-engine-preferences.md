# 完工报告 · 默认引擎开关与自定义搜索入口

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-0118 |
| 开始 | 2026-11-13 01:18 |
| 结束 | 2026-11-13 01:20 |
| 耗时 | 2 分钟 |
| 执行者 | Codex |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

为普通搜索提供默认引擎开关。支持用户添加搜索引擎、地区和网页模板后缀。设置与搜索菜单分别展示大陆直连入口、自定义入口，其他入口保持无分类标题。

## 2 做了什么

- 新增「使用自选默认引擎」及各引擎开关。选择存入本机 SQLite。系统模式沿用 SearXNG，空名单暂停普通聚合，内置手动引擎后缀可继续使用。
- 读取 SearXNG 已加载目录，严格发送勾选且已加载的引擎，核对响应来源，隔离不同名单的缓存。已导入模型的免费 AI 候选沿用同一名单。
- 「添加搜索入口」支持已加载的 SearXNG 引擎、语言地区和带 `{q}` 的网页模板。后缀可以直接输入，也可以从下拉菜单选择；网页链接在新标签页打开。
- 内置大陆入口含必应、搜狗、360 搜索和百度。独立归类用户新增的入口。保留旧搜索响应字段，只有命中自定义入口才输出新增字段。
- 本机日常 8000 已更新，验证读取真实引擎目录。

## 3 改动清单

| 路径 | 说明 |
| --- | --- |
| `apps/api/app/core/engine_preferences.py`、`engine_catalog.py`、`query_parser.py` | 本机设置、后缀验证和入口分组 |
| `apps/api/app/core/aggregator.py`、`searxng.py`、`routers/engines.py`、`routers/search.py`、`schemas.py` | 真实请求约束、设置接口、缓存和响应契约 |
| `apps/web/src/components/EngineSettingsPanel.tsx`、`components/EngineBar.tsx`、`SettingsPage.tsx`、`App.tsx` | 开关、自定义表单、后缀菜单和网页直达 |
| `apps/web/src/api.ts`、`types.ts`、`engineQuery.ts`、`url.ts`、`workspace.css` | 接口接线及样式 |
| `apps/api/tests/test_engine_preferences.py`、`scripts/engine-query.test.cjs` | 选中源、缓存隔离、旧契约及自定义路由覆盖 |
| `docs/决策与接口变更.md`、[验收资产](../assets/engine-preferences/) | 接口说明和验证证据 |

## 4 验证与证据

| 命令 | 输出 |
| --- | --- |
| `python -m pytest apps/api -q -o 'addopts='` | 退出 0，460 passed in 13.61s。首次复查发现旧 parsed 契约多两个空字段，修正后复跑全绿 |
| `node --test scripts/browser-check.test.cjs scripts/engine-query.test.cjs` | 退出 0，19 项通过 |
| `npm --prefix apps/web run build` | 退出 0，59 模块，Vite 1.12s |
| `pwsh -NoProfile -File scripts/smoke.ps1 -BaseUrl http://127.0.0.1:18185` | 退出 0，16/16 |
| `node reports/assets/engine-preferences/verify-browser.cjs` | 退出 0。设置保存刷新、Bing 单选、fr-FR、自定义引擎、网址编码、两类分组、全关及手动路由、390px 和无浏览器异常通过 |
| `python -` 隔离 ASGI 调用真实 SearXNG | 读到 263 个引擎。明日方舟普通查询只选 Bing、自定义 !localb 两次 HTTP 200，来源均仅 bing，各 9 条 |
| `python reports/assets/engine-preferences/restart-native.py` | 退出 0，8000 进程 20408 → 20240，原配置、书签、令牌和 SearXNG 均核对一致 |
| `node -` 日常 Chromium | 设置页 HTTP 200，真实目录 263 个，内置大陆分组 b/sg/so/bd，浏览器异常 0 |
| `git -c core.safecrlf=false diff --check` | 退出 0 |

证据见[浏览器](../assets/engine-preferences/browser.json)、[真实上游](../assets/engine-preferences/live.json)、[日常设置](../assets/engine-preferences/daily.json)、[部署记录](../assets/engine-preferences/restart.json)、[设置截图](../assets/engine-preferences/settings.png)、[菜单截图](../assets/engine-preferences/search.png)。

## 5 关键决策

- 自选默认名单只影响普通聚合与使用聚合候选的自定义 AI 检索。用户显式输入的内置引擎后缀沿用既有行为。
- 自定义引擎指向本机 SearXNG 已加载引擎。用户可用网页模板为其他站点创建浏览器入口。
- 多引擎请求核对已加载名单与结果出处，避免遇到未加载名称时静默使用上游默认聚合。[SearXNG 搜索参数解析](https://github.com/searxng/searxng/blob/master/searx/webadapter.py)

## 6 遗留与风险

- 大陆分组按面向大陆的入口维护，实际连通性受当前网络和上游状态影响。本轮真实选源验证只覆盖 Bing。
- 自定义地区由上游引擎解释，地区支持取决于引擎。
- 隔离数据库用于试验新增、删除和空名单。日常设置只读验收，用户可在设置页自行保存。

## 7 交接

打开 [搜索引擎设置](http://127.0.0.1:8000/settings#engine-settings)，开启自选、勾选所需引擎并保存。通过「添加搜索入口」新增后缀；示例 `关键词 frfr` 或 `关键词 !localb` 需要先登记对应入口。


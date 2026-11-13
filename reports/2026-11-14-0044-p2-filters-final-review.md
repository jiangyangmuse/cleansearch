# 完工报告 · DSH 搜索筛选、浏览器终验与真实上游复核

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261114-0044 |
| 开始 | 2026-11-14 00:44 |
| 结束 | 2026-11-14 00:51 |
| 耗时 | 8 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 部分完成 |

## 1 任务

复核 DSH 的 [搜索筛选](completed/2026-11-13-2241-p2-search-filters.md)、[浏览器终验](completed/2026-11-13-2245-browser-ui-final-acceptance.md) 与 [真实上游复核](completed/2026-11-13-2254-real-upstream-verification.md)。用 [后续复查](completed/2026-11-13-2316-browser-ui-recheck.md) 的筛选和真实验收问题作复现线索。

## 2 做了什么

- 前进、后退和翻页恢复筛选请求和页面状态。筛选变更从第一页搜索，不重复触发日常 AI。筛选面板可用 Esc、外部点击和导航关闭，窄屏控件留在视口内。站点明确提交，错误输入不发请求，分享链接可保留语言代码。
- 站点边界同时覆盖普通结果和官方目录，支持目标域与子域。时间和语言交给 SearXNG；不具备对应筛选的付费客户端和静态目录不混入该结果。
- 修复关闭去重仍合并近似标题的问题。标准只合并 canonical URL。严格对普通结果合并同名与近似标题，先提取已验证的官方入口以保护身份匹配。缓存升到 `search-v9`。
- 旧后端缺少筛选回显时显示版本提示。真实冒烟显式跳过固定样本专用的三项，指定引擎故障仍计失败。浏览器的筛选交互使用确定性结果，包括合法空态；真实筛选单独调用 API。

## 3 改动清单

| 路径 | 变更 |
| --- | --- |
| `apps/web/src/App.tsx`、`urlState.ts`、`types.ts`、`components/SearchFilters.tsx`、`components/StatePanel.tsx`、`styles.css` | 历史、浮层、输入验证和旧服务反馈 |
| `apps/api/app/schemas.py`、`routers/search.py`、`core/aggregator.py`、`core/searxng.py`、`core/normalize.py`、`db/cache.py` | 筛选边界、去重、回退和缓存 |
| `apps/api/tests/test_search.py`、`test_engine_fallback.py` | 同候选去重、官方目录站点边界、付费回退 |
| `scripts/audit-ui.cjs`、`verify-filters.cjs`、`smoke.ps1` | 稳定浏览器断言及真实环境证据 |
| `docs/决策与接口变更.md`、`docs/进展与欠账.md`、`docs/浏览器与UI优化方案.md` | 记录实际行为与验收差异 |

## 4 验证与证据

| 命令 | 实际结果 |
| --- | --- |
| `python -m pytest apps/api -q`；`python -m pytest apps/api -q -o 'addopts='` | 全量退出 0，最终 485 passed；筛选和回退专项 46 项通过。 |
| `npm.cmd --prefix apps/web run build` | TypeScript 与 Vite 通过，77 模块。 |
| `node --test scripts/extension.test.cjs scripts/css-audit.test.cjs scripts/engine-query.test.cjs` | 28 项通过。 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18207` | fixture 16/16，跳过 0。 |
| `node scripts/verify-filters.cjs http://127.0.0.1:18208` | 真实筛选 9/9。目标域 docs.python.org、官方目录空态、时间和语言回显、缓存、严格及关闭去重通过。[日志](assets/p2-filters-final-review/verify-real.log) |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18208` | 真实上游 12/13，跳过 3。Google 后缀 503 `ENGINE_UNAVAILABLE`，聚合返回 19 条、SSE 10 引用。另测 Bing 与 DuckDuckGo 后缀均 200，各 9 条。[日志](assets/p2-filters-final-review/smoke-real.log) |
| `node scripts/visual-regression.cjs --base http://127.0.0.1:18207 --out reports/assets/p2-filters-final-review/visual-baseline --update` 后复跑对比 | 12 张，变化 0、缺基线 0。前一基线只有移动搜索两张的筛选触发控件区域发生预期变化。 |
| `node --check scripts/audit-ui.cjs`；`node --check scripts/verify-filters.cjs`；`git -c core.safecrlf=false diff --check` | 退出 0。 |

| `node scripts/audit-ui.cjs --base http://127.0.0.1:18207 --test-bookmark-writes --out reports/assets/p2-filters-final-review/chromium` | 固定样本 Chromium `ALL PASS (263)`。[证据](assets/p2-filters-final-review/chromium/p0-ui-audit.json) |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18207 --channel chrome --test-bookmark-writes --out reports/assets/p2-filters-final-review/chrome` | 固定样本 Chrome `ALL PASS (263)`。[证据](assets/p2-filters-final-review/chrome/p0-ui-audit.json) |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18208 --out reports/assets/p2-filters-final-review/real` | 真实上游 Chromium `ALL PASS (260)`。按默认选项省略 3 项真实书签写入，筛选交互和补全目录使用受控数据。[证据](assets/p2-filters-final-review/real/p0-ui-audit.json) |

## 5 关键决策

- 原生自动 popover 承担浏览器关闭和焦点恢复，旧浏览器保留显式控制。站点输入通过提交生效，避免失焦时意外改变筛选。[自动 popover](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Global_attributes/popover)
- 复核保留 DSH 历史结论，区分真实冒烟执行项、跳过项与浏览器打桩项目。真实实例用现有 SearXNG、临时库、桩总结、关闭付费兜底，便于重复验证。
- 时间和语言回显证明参数送达，来源是否遵守仍取决于具体上游。[SearXNG Search API](https://docs.searxng.org/dev/search_api.html)

## 6 遗留与风险

- 真实 Google 后缀本轮仍 503，上游 Google 拒绝访问，Google CSE 冷却。Bing 与 DuckDuckGo 定向复核通过。
- 日常 8000 健康但仍为旧 fixture 后端，缺 `db_path`，OpenSearch 返回 HTML。新前端在旧后端下会提示筛选能力缺失。
- Android/iOS 真机、系统分享及读屏仍需设备验收；时间与语言未逐条核验内容。

## 7 交接

沿用当前日常服务的数据库与启动参数加载新版后端，再核对筛选回显与 OpenSearch。待 Google/CSE 恢复，复跑真实冒烟的失败项。

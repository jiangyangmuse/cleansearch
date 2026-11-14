# 完工报告 · 筛选纳入 URL 状态机（P0-1）

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261114-1247 |
| 开始 | 2026-11-14 12:47 |
| 结束 | 2026-11-14 12:48 |
| 耗时 | 2 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | fix |
| 状态 | 完成 |

## 1 任务

**目标**

按 [浏览器与 UI 复查与完善方案](../../docs/浏览器与UI复查与完善方案.md) §4.1 落地 P0-1：把搜索筛选（时间范围 / 语言 / 站点 / 去重）纳入 URL 状态机，让地址栏、界面徽标、请求体三处永远同一份筛选，前进后退与刷新都能如实还原。

**验收标准**

- 选 `week` → 浏览器后退：徽标消失、`已筛选` 摘要消失、请求体 `time_range=null`、结果回到基准。
- `week` → `day` → 后退：回到 `week`，徽标 1，摘要含「一周内」，请求体 `time_range=week`。
- 选 `site` → 后退：站点输入框清空、徽标同步、请求体 `site=null` 且沿用当前档位筛选。
- 后退之后翻页：URL 不再写回已回退的筛选。
- 只改筛选的历史条目不得被 `sameQuery && samePage` 早退吞掉。
- `urlState` 契约有 `node --test` 单测；`audit-ui.cjs` 有对应浏览器断言；全套 fixture 断言与前缀全套测试仍全绿。

**不做**

- 不改后端契约、排序、官方入口表、去重算法。
- 不做 P0-2（浮层关闭由上一轮 popover 承担）、P0-3（混版横幅）、P0-4（断点/手机范围）。
- 不新建 git 工作树：改动集中在 4 个前端/脚本文件，与他人写作用域不重叠。

## 2 做了什么

1. 筛选契约下沉到 `urlState.ts`：新增 `SearchFiltersState`、`DEFAULT_FILTERS`、`filtersFromUrl`、`sameFilters`、`withFilters`、`filterOptions`，把「URL 读写」和「请求体片段」绑在同一份结构上；`components/SearchFilters.tsx` 改为从这里取，并保留旧导出名（`Filters`/`filtersFromUrl`/`sameFilters`/`DEFAULT_FILTERS`），调用方导入路径不变，只留 UI 与中文标签。
2. `App.runSearch` 增加可选 `filters` 参数：取到就同步写回 `filtersRef`，本次调用的地址栏（`withFilters`+`writeUrl`）与请求体（`filterOptions`）都读这一个对象，杜绝「URL 用新筛选、请求读旧 ref」。
3. `popstate`：`sameSearch` 比较 `q/literal/page` 加四个筛选字段；只改筛选的历史条目传 `filters: nextFilters`、`paging=false`、`urlMode="none"`、`filterChange`，重新检索但不写历史；空查询回退仍先把筛选重置为 URL 值再回空闲态。`changeView`/`applyFilters` 的 URL 写入同样改走 `withFilters`。
4. 新增 `scripts/url-state.test.cjs`（7 项）：URL 往返、默认值不入地址栏、非法 `page/range/dedupe/lang/site` 归一、筛选差异逐项识别、`withFilters` 合并、请求体片段空值转 `null`。
5. `scripts/audit-ui.cjs` 补两条浏览器断言（两档时间范围来回回退、回退清空站点限定后输入框与请求同步），并修掉 1024px 断点断言里「改视口后立刻量右侧栏」的竞态（先等 `.workspace-side` 有尺寸再量）。
6. 文档同步：`docs/决策与接口变更.md` 增 «2026-11-14 · 筛选纳入 URL 状态机（P0-1）»；方案 §4.1 加落地状态与报告指针。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `apps/web/src/urlState.ts` | 修改 | 筛选契约与 `filtersFromUrl/sameFilters/withFilters/filterOptions`（+48 行） |
| `apps/web/src/App.tsx` | 修改 | `runSearch` 显式 `filters` 参数、`popstate` 传还原筛选、URL 写入统一走 `withFilters` |
| `apps/web/src/components/SearchFilters.tsx` | 修改 | 只留 UI 与标签，契约改为从 urlState 导入并原样再导出 |
| `scripts/url-state.test.cjs` | 新增 | URL/筛选契约单测 7 项（`node --test`） |
| `scripts/audit-ui.cjs` | 修改 | 新增 2 条筛选历史断言；1024px 断点断言改为等右侧栏挂载后再量 |
| `docs/决策与接口变更.md` | 修改 | 记录 P0-1 的契约位置与判定口径 |
| `docs/浏览器与UI复查与完善方案.md` | 修改 | §4.1 加落地状态 |
| `reports/assets/p0-1-filter-url-state/` | 新增 | `audit.log`（262 项明细）、`pytest.log`、`audit/`（截图与 `p0-ui-audit.json`） |

> 报告里 §3 的"自动采集（git）"清单未保留：本轮工作区还有他人既有的文档分类、报告搬迁与脚本改动，不属于本任务，混进来会误导下一个接手的人。

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `npm --prefix apps/web run build` | 通过 | `tsc --noEmit` + Vite，77 模块，`App-*.js` 70.26 kB |
| `python -m pytest apps/api -q -o addopts=` | 通过 | `485 passed in 9.54s`（[日志](../assets/p0-1-filter-url-state/pytest.log)） |
| `node --test scripts/extension.test.cjs scripts/css-audit.test.cjs scripts/engine-query.test.cjs scripts/url-state.test.cjs` | 通过 | `tests 35 / pass 35 / fail 0`，其中新增 urlState 7 项全绿 |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18411 --out reports/assets/p0-1-filter-url-state/audit` | 通过 | `ALL PASS (262)`，比上一轮 fixture 口径多 2 项（[明细](../assets/p0-1-filter-url-state/audit.log)） |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18411` | 通过 | `冒烟通过 16/16，跳过 0` |
| `node --check scripts/audit-ui.cjs` | 通过 | exit 0 |

关键断言原文（`audit.log`）：

- `PASS 历史后退后翻页不写回旧筛选`
- `PASS 时间范围连改两档后回退还原上一档筛选 · day=day back=week`
- `PASS 回退清掉站点限定后输入框与请求同步 · site="" badge=1 opts={"safe":true,"literal":false,"time_range":"week","language":null,"site":null,"dedupe":"normal"}`
- `PASS 刷新后筛选从地址栏还原 · badge=3 note=已筛选：一周内 · site:example.com · 严格去重`

隔离实例：`serve.ps1 -Provider fixture -Port 18411 -SkipBuild`（临时库 `data/cs.db`，未触碰日常 8000）。

未验证：`--test-bookmark-writes` 口径（需写书签）与本轮无关，仍按默认省略 3 项；真实 SearXNG 上游的筛选回显沿用上一轮 `verify-filters.cjs` 结论，本轮未重跑。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 筛选契约放 `urlState.ts`，组件只消费 | 继续放 `SearchFilters.tsx`，App 直接从组件导入 | URL 与请求体是同一件事的两面；放组件里会导致 urlState 单测要么绕到组件，要么不敢测 |
| `runSearch` 加显式 `filters` 参数 | 依赖 `filtersRef` 的赋值顺序 | ref 是"当前值"，popstate 需要"这次要用的值"；显式参数让调用点自己决定，不受 React 批次时机影响 |
| 后退仍用 `urlMode="none"` 且 `paging=false` | 复用 `paging` 保留旧列表 | 筛选变化会改变结果集，留着旧列表会闪出与地址栏不符的条目 |
| 保留 `SearchFilters.tsx` 的旧导出名 | 全仓库改导入路径 | 改动面小，App 只改一行；减少与他人改动的冲突 |
| 修 1024px 断点断言的竞态，而不是改判定 | 放宽成"主列 ≥560" | 断点本身是 P0-4 的活；这里只保证现有断言稳定可复现 |

## 6 遗留与风险

- 本轮没有新增手机/窄屏路径：`390/320` 的筛选面板定位属 P0-2/P0-4，断言仍依赖已通过的 popover 实现。
- `filterChange: !filtersUnchanged` 让后退到"只差筛选"的历史条目时不再清空 AI 侧栏（`urlMode="none"` 本来也不重发 AI 请求）；如果后续要求后退时同步收起 AI 面板，需要另加一条显式规则。
- 日常 8000 仍是旧 fixture 后端，新前端在它上面依旧会提示"筛选能力缺失"（P0-3 的活），本轮未动。
- `audit-ui.cjs` 的真实上游口径建立在"请求体 + `meta.filters`"上；上游条数仍不可作为断言前提（复查 R-12 未解）。

## 7 交接

**下一个人第一件事**

接着做 P0-2（方案 §4.2 已完成大半）：在 `SearchFilters` 里补"路由/查询变化即关闭"的断言，或在 `390/320` 上把面板改成视口对齐的固定面板，然后跑 `node scripts/audit-ui.cjs --base http://127.0.0.1:<fixture 端口>`。

**相关文件**

- 契约：`apps/web/src/urlState.ts`、`apps/web/src/components/SearchFilters.tsx`
- 状态机：`apps/web/src/App.tsx`（`runSearch` 的 `filters` 参数、`popstate`）
- 断言：`scripts/url-state.test.cjs`、`scripts/audit-ui.cjs`（"P2-7 搜索筛选"段与 1024px 断点段）
- 证据：`reports/assets/p0-1-filter-url-state/`

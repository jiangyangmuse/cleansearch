# 完工报告 · P2 搜索筛选能力

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-2241 |
| 开始 | 2026-11-13 22:41 |
| 结束 | 2026-11-13 22:41 |
| 耗时 | 不到 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

**目标**

按 [浏览器与 UI 优化方案](../../docs/浏览器与UI优化方案.md) §7 第 7 条落地筛选能力：后端 `opts` 扩展时间范围/语言/站点限定/去重强度与缓存键升级，前端加可分享的筛选条。

**验收标准**

- `opts` 四类字段合法值生效并回显在 `meta.filters`；非法值 422。
- 同一查询换筛选条件不命中旧缓存（`cached=false`），重复同条件命中。
- 去重强度三档行为：off 全保留、normal 合并 canonical URL、strict 再合并同名标题。
- 前端筛选条默认收起；改时间范围/站点/去重都会写入请求与地址栏；刷新可还原；重置清空。
- 既有 245 项浏览器断言不回归；pytest、构建、视觉基线通过。

**不做**

- 站点限定不做多站点 OR 语法（只接受单个域名）。
- 未做筛选条件持久化到 localStorage（以 URL 为准）。

## 2 做了什么

1. **后端字段**：`SearchOpts` 增加 `time_range`/`language`/`site`/`dedupe` 与两个校验器（语言码形如 `zh`、`pt-BR`；站点只收域名，自动去协议、路径与 `www.`）。
2. **上游透传**：`SearxngClient.search` 支持 `time_range`、`language`（覆盖地区推导）、`site`（拼成 `site:域名`），`Aggregator.search`/`_search_explicit` 全链路透传。
3. **去重强度**：`normalize.apply_dedupe(results, mode)` 实现 off/normal/strict；`strict` 用现有标题指纹再合并同标题。
4. **缓存**：`search_key` 增加 `filters` 元组并升版 `search-v7`，筛选条件参与键计算。
5. **回显**：`SearchMeta.filters`（`SearchFilters`）返回本次生效条件，三个构造点（缓存命中/正常/快捷无结果）都填。
6. **前端**：新增 `SearchFilters` 组件（chips + 两个 select + 站点输入 + 重置），`App` 里维护 `filters` 与 `filtersRef`，改动后从第 1 页重搜并 push；`urlState` 增加 `range/lang/site/dedupe` 读写，`popstate` 还原时带上筛选。
7. **测试**：后端新增筛选校验/缓存隔离/去重三档用例；`scripts/audit-ui.cjs` 新增 6 项浏览器断言。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `apps/api/app/schemas.py` | 修改 | SearchOpts 四字段 + 校验；SearchFilters；meta.filters |
| `apps/api/app/core/searxng.py` | 修改 | time_range/language/site 参数 |
| `apps/api/app/core/aggregator.py` | 修改 | 透传到默认/显式两条路径 |
| `apps/api/app/core/normalize.py` | 修改 | `apply_dedupe` 三档 |
| `apps/api/app/db/cache.py` | 修改 | `search_key` 增加 filters，升版 v7 |
| `apps/api/app/routers/search.py` | 修改 | 传参、缓存键、`_filters()` 回显 |
| `apps/api/tests/test_search.py`、`test_cache.py`、`test_normalize_dedupe.py`、`test_engine_fallback.py` | 修改/新增 | 筛选校验、缓存隔离、去重、上游透传 |
| `apps/web/src/components/SearchFilters.tsx` | 新增 | 筛选条组件 |
| `apps/web/src/App.tsx`、`urlState.ts`、`api.ts`、`styles.css` | 修改 | 状态、URL、请求体、样式 |
| `scripts/audit-ui.cjs` | 修改 | 新增 6 项断言（共 249 项） |
| `docs/决策与接口变更.md`、`docs/浏览器与UI优化方案.md` | 修改 | 契约与完成标注 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `python -m pytest apps/api -q` | 通过 | 481 项（476 + 新增 5），`[100%]` 无 F/E |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18197 --out reports/assets/ui-p2` | 通过 | `ALL PASS (249)`：筛选默认收起、时间范围/站点/去重写入请求与地址栏、徽标与摘要、刷新还原、重置清空 |
| `node --test scripts/css-audit.test.cjs scripts/extension.test.cjs` | 通过 | 10 项 |
| `node scripts/visual-regression.cjs --base http://127.0.0.1:18197` | 通过 | 重建基线后对比 12 张「变化 0」 |
| `npm --prefix apps/web run build` | 通过 | 76 modules，主包 236.35 kB |
| 环境 | — | 验收用独立 `serve.ps1 -Provider fixture -Port 18197`，验完已停 |

**证据文件**

- 审计结果：`reports/assets/ui-p2/p0-ui-audit.json`
- 视觉基线：`reports/assets/p2-extension-vitals-review/visual-baseline/`（本轮更新 12 张）

**未验证**

- 真实 SearXNG 的 `time_range`/`language`/`site:` 组合效果未实测（8888 仍不可用）；fixture 模式不识别筛选，只验证契约与回显。
- 站点限定只接受单域名，多站点/子域通配未支持。
- 去重 strict 的标题指纹对极短标题可能过度合并。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 站点限定用 `site:` 语法 | 上游参数过滤 | SearXNG 原生支持 `site:`，改动最小且各引擎通用 |
| 语言显式值覆盖地区推导 | 合并成两个参数 | SearXNG 只有一个 `language` 参数，显式优先级更高更可预期 |
| 去重作为搜索选项 | 独立「查看更多」按钮 | 不同用户对噪音容忍度不同，交给请求控制更直接 |
| 筛选写进 URL 而非 localStorage | 仅本地记忆 | URL 可分享、可回退、可刷新还原，符合「浏览器原生语义」原则 |

## 6 遗留与风险

- fixture provider 不执行筛选，自检看到的仍是同一批样本；真实效果需接 SearXNG 复核。
- 筛选变化会重新请求并从第 1 页开始，若用户在第 5 页筛选会丢失页码（符合预期但未提示）。
- `language` 允许 2–4 位地区后缀，但上游是否识别取决于 SearXNG 配置。

## 7 交接

**下一个人第一件事**

P2 已全部完成。接入真实 SearXNG 后复跑 `time_range`/`language`/`site:` 的组合，并观察筛选对上游耗时与结果数的影响；随后可进入 P3（导出/分享、观测面板等方案剩余项）。

**相关文件**

- 方案：`docs/浏览器与UI优化方案.md`（§7 全部完成）
- 决策：`docs/决策与接口变更.md`（2026-11-13 · P2 搜索筛选能力）
- 实现：`apps/api/app/schemas.py`、`apps/api/app/core/normalize.py`、`apps/web/src/components/SearchFilters.tsx`
- 验收：`scripts/audit-ui.cjs`、`reports/assets/ui-p2/`
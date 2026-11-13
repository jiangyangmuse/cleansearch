# 完工报告 · P1 错误态产品化与空态分类

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-1755 |
| 开始 | 2026-11-13 17:55 |
| 结束 | 2026-11-13 17:56 |
| 耗时 | 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

**目标**

按 [浏览器与 UI 优化方案](../../docs/浏览器与UI优化方案.md) §6 落地 P1 第 9、10 条：错误态产品化（“本机搜索服务未连接”+ 重试/打开设置，诊断命令仅 debug/fixture 可见）与空态/分类提示（换关键词、取消引擎后缀、查看全部；分类页显示本页/全部条数）。

**验收标准**

- 断网时标题是「本机搜索服务未连接」，操作为「重试」+「打开设置」。
- 非 debug/非 fixture 不出现诊断详情；`?debug=1` 出现且默认收起，展开含错误码与 `curl`。
- 空结果给「换关键词」（点击后焦点进搜索框）；带 `!g` 的空结果额外给「取消引擎后缀 !g」，点击按原词重搜。
- 分类视图显示 `本页 N 条 · 全部 M 条`；分类本页无命中时说明还有其它结果并给「查看全部结果」。
- 既有 148 项断言不回归；pytest 与前端构建通过。

**不做**

- P1 余下条目（主题细节、书签快捷栏刷新细项、AI 工具流控制、设置页增强、旧页面移动端）。
- 不改错误码集合与后端错误文案。

## 2 做了什么

1. **StatePanel 重写**：`ErrorState` 按错误类型给三种标题与说明，操作区固定「重试」+「打开设置」（`/settings#engine-settings`）；网络错误不再重复展示后端 message（与正文说明重复），其它错误保留原文。`EmptyState` 增加 `categoryLabel/otherCount/suffix/onChangeKeyword/onClearSuffix/onViewAll`。
2. **诊断门控**：`App` 新增 `debugMode`（进页面读一次 `?debug=1`）——搜索会重写地址栏，不能每次现读 URL；配合既有的 `showSamples`（provider=fixture）决定是否渲染 `<details>诊断详情</details>`，默认收起。
3. **空态动作**：`focusSearch()` 聚焦并全选搜索框；`clearSuffix()` 去掉末尾 `!code` 后按原词重搜（去后缀后不足 2 字则不显示按钮）。
4. **分类计数与空分类**：分类视图加 `本页 N 条 · 全部 M 条`；分类无命中改成独立空态块，说明「本页还有 M 条其它结果」并给「查看全部结果 / 换关键词」。
5. **验收脚本**：新增 12 项断言，用可控响应构造断网、`?debug=1`、空结果、带后缀空结果、分类计数与分类空态。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `apps/web/src/components/StatePanel.tsx` | 重写 | 错误分级标题、操作区、诊断详情；空态动作 |
| `apps/web/src/App.tsx` | 修改 | `debugMode`、`focusSearch`、`clearSuffix`、分类计数与空分类块 |
| `apps/web/src/styles.css` | 修改 | `.state__actions`/`.state__diagnostics`/`.workspace-results__count` |
| `scripts/audit-ui.cjs` | 修改 | 新增 12 项断言（共 160 项） |
| `reports/assets/ui-p1/` | 修改 | 新增 `desktop-error-state.png`、`desktop-empty-state.png` 与最新审计 JSON |
| `docs/决策与接口变更.md` | 修改 | 记录错误分级、诊断门控、空态规则 |
| `docs/浏览器与UI优化方案.md` | 修改 | §6 第 9、10 条标注已完成 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18190 --out reports/assets/ui-p1` | 通过 | `ALL PASS (160)`：断网标题、重试+打开设置、非 debug 无诊断、`?debug=1` 有且默认收起、诊断含 curl、换关键词聚焦、取消后缀重搜、`本页 1 条 · 全部 3 条`、分类空态跳全部 |
| `npm --prefix apps/web run build` | 通过 | 69 modules，JS 328.62 kB，CSS 54.03 kB |
| `python -m pytest apps/api -q` | 通过 | 465 项，`[100%]` 无 F/E |
| 环境 | — | 本次验收用独立进程 `serve.ps1 -Provider fixture -SkipBuild -Port 18190`（全新库），8000 上的旧进程未动 |

**证据文件**

- 审计结果：`reports/assets/ui-p1/p0-ui-audit.json`
- 截图：`desktop-error-state.png`（诊断展开）、`desktop-empty-state.png`（带引擎后缀的空态）

**未验证**

- 真实 SearXNG 上游的错误码分布未复跑；`UPSTREAM_BAD_RESPONSE` 等分支只做了类型映射，未逐一造错。
- 移动端错误/空态只复用同一组件，未单独截图；读屏朗读 `role=alert` 未实机验证。
- 分类计数在真实多页、跨页场景未验（当前仅单页可控数据）。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 诊断详情用原生 `<details>` | 弹窗 | 开发信息默认收起、零 JS、可键盘操作 |
| `debugMode` 进页面读一次 | 每次读 `location.search` | 搜索会 `replaceState` 重写地址栏，现读会丢掉 `debug` |
| 断网不重复显示后端 message | 原样展示 | 后端 message 也在讲「确认 FastAPI」，与正文重复 |
| 取消后缀需剩余 ≥2 字 | 总是显示按钮 | 去后缀后只剩 1 个字时搜不了，按钮会变谎言 |
| 分类空态用独立块而不是一行提示 | 保留一行 `本页没有` | 一行容易被读成“全站没有这个分类” |

## 6 遗留与风险

- `?debug=1` 只在首次进入时生效；如果用户先正常进入再想开诊断，需要刷新带参数。
- 分类计数依赖 `meta.total`（本页三档合计），不是全站总数——文案已写「本页/全部（本页合计）」，但“全部”仍可能被理解成全站，后续接后端总数字段再改文案。
- 空态动作没有埋点，无法衡量“换关键词”使用率。

## 7 交接

**下一个人第一件事**

在真实 SearXNG 环境跑 `node scripts/audit-ui.cjs` 复核错误码分布与分类计数，然后做 P1 第 11、12 条：主题细节（`:root[data-theme=dark]{color-scheme:dark}`、`meta[name=theme-color]` 同步、`prefers-reduced-motion` 关掉 spinner/闪烁）+ 书签快捷栏刷新（`visibilitychange`/`pageshow`/删除事件，移动端进抽屉、最多 6 条 + 管理入口）。

**相关文件**

- 方案：`docs/浏览器与UI优化方案.md`（§6 第 9、10 条已标注完成）
- 决策：`docs/决策与接口变更.md`（2026-11-13 · P1 错误态产品化与空态/分类提示）
- 实现：`apps/web/src/components/StatePanel.tsx`、`apps/web/src/App.tsx`
- 验收：`scripts/audit-ui.cjs`、`reports/assets/ui-p1/`
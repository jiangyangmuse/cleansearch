# 完工报告 · P2 分享文案、扩展增强与性能

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-2207 |
| 开始 | 2026-11-13 22:07 |
| 结束 | 2026-11-13 22:07 |
| 耗时 | 不到 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

**目标**

按 [浏览器与 UI 优化方案](../../docs/浏览器与UI优化方案.md) §7 落地 P2 第 4–6 条：结果卡分享文案含标题+链接；扩展补图标/快捷键/omnibox/options/popup 增强/右键选中文本；前端做路由级拆包、卡片 memo 与长列表 `content-visibility`。

**验收标准**

- 分享 payload 同时带 `title`、`text`（标题+换行+链接）与 `url`。
- 扩展 manifest 有 16/32/48/128 图标与 `default_icon`、`commands.save-page`、`omnibox.keyword=cs`、`options_ui`；右键上下文含 page/link/selection。
- 首屏不加载设置页/书签页分包，进入 `/settings` 时按需加载；离线打开未访问过的 `/settings` 仍渲染完整壳。
- 结果卡使用 `content-visibility: auto`，且菜单展开时不被裁切。
- 既有 228 项浏览器断言不回归；`node --test scripts/extension.test.cjs` 通过；pytest 与构建通过。

**不做**

- popup 里的分组/标签（服务端对 token 外部写入只接受 url/title，硬加会 403，已在决策里记录）。
- favicon 并发限制、LCP/INP/CLS 采集（记为 P2 剩余项）。

## 2 做了什么

1. **分享**：ResultCard 的 `navigator.share` 增加 `text: 标题 + 换行 + 链接`，兼容只读 text 的平台。
2. **扩展图标**：Pillow 生成 16/32/48/128 四个 PNG（品牌绿 + 白色放大镜），写入 `icons/` 并接上 `icons` 与 `action.default_icon`。
3. **扩展能力**：`commands.save-page`（Ctrl/⌘+Shift+S）→ `saveActiveTab()`；`omnibox` 关键字 `cs` → 打开本机 `/?q=`；右键菜单覆盖 page/link/selection，选中文本作为标题前缀；popup 增加「打开书签页 / 打开搜索 / 扩展设置」与深色、focus-visible。
4. **options 页**：新增 `options.html/js/css`，保存 API/token、测试 `/api/health` 并用一次故意非法的写入探测 token 权限（不会真的写库），展示快捷键与入口说明。
5. **性能**：`main.tsx` 路由级 `React.lazy` + `Suspense`（fallback `.app-boot`）；`ResultCard` 改 `memo` 并把 `onSelect` 换成 `onSelectId` 保持 props 稳定；`.group__list > .card` 加 `content-visibility: auto` + `contain-intrinsic-size`，用 `:not(:has(.card__actions[open]))` 在菜单打开时取消 containment。
6. **构建期 SW 注入**：`apps/web/sw.js` 的占位符由 `vite.config.ts` 的 `closeBundle` 注入（版本 = index.html sha256 前 20 位，壳表含全部 JS/CSS 分包），保证离线打开未访问路由可用。
7. **扩展静态检查**：新增 `scripts/extension.test.cjs`（6 个用例）。
8. **测试适配**：离线 `/settings` 断言改为等待 heading 出现（路由改成懒加载后不能立即 isVisible）。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `apps/extension/manifest.json` | 修改 | 图标、default_icon、commands、omnibox、options_ui |
| `apps/extension/background.js` | 修改 | 命令/omnibox/右键选中文本、菜单重建 |
| `apps/extension/options.html`/`options.js`/`options.css` | 新增 | 扩展设置页 |
| `apps/extension/popup.html`/`popup.js`/`popup.css` | 修改 | 链接入口、深色、focus-visible |
| `apps/extension/icons/icon-{16,32,48,128}.png` | 新增 | 扩展图标 |
| `apps/web/src/main.tsx` | 修改 | 路由级 `React.lazy` + `Suspense` |
| `apps/web/src/components/ResultCard.tsx` | 修改 | memo、onSelectId、分享文案 |
| `apps/web/src/components/ResultList.tsx` | 修改 | 传 `onSelectId` |
| `apps/web/src/styles.css` | 修改 | `content-visibility` 与 `.app-boot` |
| `apps/web/vite.config.ts` | 修改 | SW 注入插件（closeBundle，20 位版本号） |
| `scripts/extension.test.cjs` | 新增 | manifest/图标/入口静态检查 |
| `scripts/audit-ui.cjs` | 修改 | 新增性能断言并修离线懒加载等待（共 239 项） |
| `docs/决策与接口变更.md`、`docs/浏览器与UI优化方案.md` | 修改 | 口径与完成标注 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `node --test scripts/extension.test.cjs` | 通过 | 6 项：manifest 字段、图标尺寸、commands、omnibox、options/popup 引用、右键上下文 |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18195 --out reports/assets/ui-p2` | 通过 | `ALL PASS (239)`：含 content-visibility=auto、首屏不含 SettingsPage/BookmarkPage 分包、`/settings` 按需加载分包、离线未访问路由渲染完整壳 |
| `npm --prefix apps/web run build` | 通过 | 73 modules；页面分包 App/BookmarkPage/ToolsPage/PageSummaryPage/SettingsPage 各 4–23 kB；dist/sw.js 注入后无占位符 |
| `python -m pytest apps/api -q` | 通过 | 473 项（本轮未改后端） |
| 环境 | — | 验收用独立 `serve.ps1 -Provider fixture -Port 18195`，验完已停 |

**证据文件**

- 审计结果：`reports/assets/ui-p2/p0-ui-audit.json`
- 扩展图标：`apps/extension/icons/`

**未验证**

- 扩展真实加载（chrome://extensions 手动加载）与快捷键/mnibox/options 的交互未在浏览器里跑；本轮是静态检查 + 既有 linter。
- 真机 Web Share 面板与 Android 分享未验。
- LCP/INP/CLS 未采集；favicon 并发未限制。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 路由级 lazy 只拆页面，不拆搜索页内部 | 全部组件级拆包 | 页面边界清晰、收益大；组件级拆包会增加瀑布请求 |
| `onSelectId` 替代闭包回调 | 用 `useCallback` 包每个卡片回调 | props 稳定才能让 `memo` 生效；列表里不能为每张卡建闭包 |
| `content-visibility` 加 `:has` 例外 | 全局关闭 / 菜单用 popover | 保留长列表优化，同时避免 paint containment 裁掉绝对定位菜单 |
| SW 壳表在构建期注入 | 运行时扫描 / 预缓存单一入口 | 懒加载分包在运行时拿不到清单；构建期知道全部文件名才能离线开任意路由 |
| popup 不做分组/标签 | 强行调用 PATCH | 服务端对 token 外部写入只接受 url/title，改服务端语义超出本轮范围 |

## 6 遗留与风险

- **并发覆盖风险（已发生）**：本轮开始时 `apps/web/sw.js`、`vite.config.ts` 等处已有工作区里未提交的 SW 构建注入实现（另一会话）。我重写 `vite.config.ts` 时覆盖了它的插件，只能按 `sw.js` 里的三个占位符重建等价插件（含 20 位版本号约定）。后续动公共入口/构建配置前必须先 `git status` + `grep` 关键符号。
- 扩展版本号改为 0.2.0，但未在真实 Chrome 里加载验证。
- `content-visibility` 会改变长列表的占位高度，快速滚动时可能出现一次重排。
- 分享 `text` 拼接标题与链接，个别平台可能重复显示标题。

## 7 交接

**下一个人第一件事**

P2 剩余：Web Share 真机、扩展实际加载与快捷键验证、favicon 并发/尺寸限制、Web Vitals 采集（LCP/INP/CLS）、筛选能力（时间/语言/站点）与设计系统清理（旧 `.header`/`.main`/`.summary-toggle` 死样式）。

**相关文件**

- 方案：`docs/浏览器与UI优化方案.md`（§7 第 4–6 条已标注）
- 决策：`docs/决策与接口变更.md`（2026-11-13 · P2 分享文案、扩展增强与性能）
- 实现：`apps/extension/`、`apps/web/src/main.tsx`、`apps/web/vite.config.ts`、`apps/web/src/components/ResultCard.tsx`
- 验收：`scripts/audit-ui.cjs`、`scripts/extension.test.cjs`、`reports/assets/ui-p2/`
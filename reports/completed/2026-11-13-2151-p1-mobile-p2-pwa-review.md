# 完工报告 · DSH 旧页面移动端与 PWA 两轮复核

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-2151 |
| 开始 | 2026-11-13 21:51 |
| 结束 | 2026-11-13 21:56 |
| 耗时 | 5 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 完成 |

## 1 任务

复核 [DSH 21:14 旧页面移动端](2026-11-13-2114-p1-legacy-mobile.md) 和 [DSH 21:23 PWA 应用外壳](2026-11-13-2123-p2-pwa-shell.md)，验证窄屏表单、示例总结、安装、离线、分享、更新和 OpenSearch。

原验收在干净隔离库等待现存书签卡片超时。原 API 测试仍断言 GET 分享，而清单已改为 POST。旧报告与历史台账保留。本轮用固定浏览器样本验证布局，并更新 POST 契约测试。

## 2 做了什么

- 收到链接分享时，窄屏展开添加表单并预填。键盘仍可操作原生折叠。书签主要操作至少 44px，保存期间防止重复提交。
- 单页总结示例支持键盘启动并将焦点交给网址框。带 `u` 的直接打开只发起一次请求，离页中止客户端请求，失败后仍可选示例。
- Vite 按构建内容生成 worker 版本、首页校验值和静态资源清单。完整预缓存成功后才安装，旧版本在失败时继续工作。应用路由可离线打开，API 和安全跳转仍直连。
- 更新提示读取真实等待版本，用户确认后等待对应 worker 接管再刷新。一次性安装提示失败时在设置页显示反馈。
- 同源 multipart 导航用 303 进入书签页，字段通过 URL 片段传递，随后清除。OpenSearch 由当前部署来源生成绝对搜索模板。服务对缺失的构建资源返回 404。

## 3 改动清单

| 路径 | 变更 |
| --- | --- |
| `apps/web/src/BookmarkPage.tsx`、`apps/web/src/PageSummaryPage.tsx`、`apps/web/src/api.ts`、`apps/web/src/workspace.css`、`apps/web/src/styles.css` | 窄屏表单、分享预填、焦点与请求 |
| `apps/web/vite.config.ts`、`apps/web/sw.js`、`apps/web/public/offline.html` | 按构建完整预缓存与离线；移出原 public worker |
| `apps/web/src/swRegister.ts`、`apps/web/src/components/UpdateToast.tsx`、`apps/web/src/pwa.ts`、`apps/web/src/SettingsPage.tsx` | 安装和等待版本更新 |
| `apps/web/index.html`、`apps/web/src/main.tsx` | 恢复首屏主题引导并移除重复写入 |
| `apps/api/app/main.py` | OpenSearch 动态响应，替代原静态 XML；静态资源和 worker 响应头 |
| `apps/api/tests/test_search.py`、`apps/api/tests/test_tools.py`、`scripts/audit-ui.cjs` | 契约与真实浏览器回归 |
| `docs/决策与接口变更.md`、`docs/浏览器与UI优化方案.md`、`docs/进展与欠账.md` | 实现和验收边界 |

## 4 验证与证据

| 命令 | 实际结果 |
| --- | --- |
| `python -m pytest apps/api -q`；`python -m pytest apps/api -q -o 'addopts='` | 两次退出 0，474 passed。 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18199` | 16/16，侧栏 SSE 10 个引用。 |
| `npm.cmd --prefix apps/web run build` | TypeScript 和 Vite 通过，73 模块。生成 `index-C3cAHl-_.js` 和带预缓存表的 `sw.js`。 |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18199 --test-bookmark-writes --out reports/assets/p1-mobile-p2-pwa-review/chromium` | `ALL PASS (239)`。[Chromium JSON](../assets/p1-mobile-p2-pwa-review/chromium/p0-ui-audit.json) |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18199 --channel chrome --test-bookmark-writes --out reports/assets/p1-mobile-p2-pwa-review/chrome` | `ALL PASS (239)`。[Chrome JSON](../assets/p1-mobile-p2-pwa-review/chrome/p0-ui-audit.json) |
| `node` 定向运行 Playwright `launchPersistentContext({ channel: "chrome" })` 后请求 CDP `Page.getAppManifest`、`Page.getInstallabilityErrors` | 清单成功解析，清单和安装资格错误均为 0。[安装资格证据](../assets/p1-mobile-p2-pwa-review/chrome/installability.json) |
| `node --test scripts/engine-query.test.cjs`、`node --check scripts/audit-ui.cjs`、`node --check apps/web/dist/sw.js`、`git -c core.safecrlf=false diff --check` | Node 18 项通过，语法与 diff 检查退出 0。 |
| `Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/opensearch.xml` | 日常 8000 返回 HTML，尚未加载新后端的 OpenSearch 路由。 |

独立浏览器上下文真实安装 worker 后断网，新标签可打开从未访问过的设置页，API 和 `/go` 请求失败，未知路径显示离线页。测试代理模拟新版资源 503，旧缓存仍在；再提供完整新 worker，验证等待、稍后、重新发现和确认接管。分享通过真实 multipart 导航提交，后续 GET 只请求 `/bookmarks`。

## 5 关键决策

- 预缓存目录和 worker 版本由 Vite 生成，首页校验拦截部署过程中的版本错配。保留已验证的缓存，避免把部分新版误当作完整离线壳。[Service Worker 生命周期](https://web.dev/articles/service-worker-lifecycle)
- 保留 POST 分享，表单返回 303。预填内容走片段，避免由随后的 GET 发送至服务端。[Web Share Target](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Manifest/Reference/share_target)
- OpenSearch 用部署的实际主机和端口生成浏览器可解析的绝对模板。[Chromium OpenSearch 解析器](https://chromium.googlesource.com/chromium/src/+/refs/tags/145.0.7582.1/components/search_engines/template_url_parser.cc)

## 6 遗留与风险

- Android/iOS 真机的系统安装、分享面板和移动读屏待复验。桌面 Chrome 已通过浏览器协议安装资格检查，自动化覆盖 multipart 导航和安装提示失败反馈。
- 三个公网总结示例实际尝试均得到 403，本机 DNS 将这些域名解析至 198.18.0.0/15，触发已有的非公网地址保护。浏览器已验证提交、焦点和请求次数。公网抓取需在返回真实公网地址的网络复验。
- 日常 8000 进程需加载新版后端后复验 OpenSearch。已安装的 PWA 收到新版提示后可按「立即更新」。

## 7 交接

沿用日常服务现有数据库和启动参数加载新版后端，复查 `/opensearch.xml` 的 MIME 和绝对模板。有真机时补验系统安装、分享与读屏，有正常公网解析时重试示例总结。

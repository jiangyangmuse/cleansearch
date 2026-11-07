# 完工报告 · M8 一键添加验收与加固

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261106-2214 |
| 开始 | 2026-11-06 22:14 |
| 结束 | 2026-11-06 22:15 |
| 耗时 | 1 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 部分完成 |

## 1 任务

**目标**

独立验收 M8 的 bookmarklet、浏览器扩展与 PWA 分享，修复跨域权限、扩展地址校验和分享文本预填。

**验收标准**

- 跨域只允许带有效 token 的最小添加请求，非回环 Host 和书签读、改、删均被拒绝。同源操作继续可用。
- 两个本机源实测 bookmarklet 保存。模拟连接被阻断时可进入预填页，预填不写库。
- 运行全量测试、构建、冒烟和扩展弹窗行为验证。记录原生扩展安装和手机系统分享的验证边界。

**不做**

- 本轮范围为已有 M8 通道，所有收藏操作使用独立临时库和合成页面。

## 2 做了什么

1. 只接收回环 Host，关闭非本机域名经重绑定访问 token 的入口。跨域 token 只允许 `POST /api/bookmarks` 的网址和标题，重复提交不改写旧记录，响应只返回是否重复。
2. token 端点禁止缓存，首次创建使用独占文件写入。扩展校验本机 HTTP 地址、拒绝重定向。Compose 在持久卷保存 token。
3. bookmarklet 直连受阻时可经确认打开本机书签预填。书签页新增一键添加入口，分享支持链接字段与带链接的文本，读取后移除地址栏的分享参数。
4. PWA 补齐 192 与 512 像素的项目图标。优化工具页提示，明确同一设备须可访问服务。

## 3 改动清单

| 路径 | 说明 |
| --- | --- |
| `apps/api/app/main.py`、`apps/api/app/core/tokens.py`、`apps/api/app/routers/tools.py` | Host 与跨域约束、token 创建和读取、bookmarklet 降级 |
| `apps/api/app/routers/bookmarks.py`、`apps/api/app/db/repo.py`、`apps/api/app/schemas.py` | 一键添加字段及响应收口，重复项保持旧记录 |
| `apps/api/tests/conftest.py`、`apps/api/tests/test_tools.py` | 本机 Host、跨域越权、token 并发、图标回归 |
| `apps/extension/popup.js`、`apps/extension/popup.html`、`apps/extension/README.md` | 本机配置验证、超时、重定向防护、反馈 |
| `apps/web/src/BookmarkPage.tsx`、`apps/web/src/ToolsPage.tsx` | 分享预填、入口和文案 |
| `apps/web/public/manifest.webmanifest`、`icon-192.png`、`icon-512.png` | 清单图标资源 |
| `docker-compose.yml`、`README.md`、`docs/决策与接口变更.md` | token 持久化、接口与使用边界 |
| `reports/2026-11-06-2214-m8-capture-acceptance.md`、`reports/INDEX.md` | 验收证据与台账 |

## 4 验证与证据

| 命令或操作 | 结果 | 关键输出 |
| --- | --- | --- |
| `python -m pytest apps/api -q -o 'addopts='` | 通过 | 最终版 `239 passed in 2.85s`，包括伪造 Host、跨域越权、并发 token、IPv6 基址及清单图标 |
| `npm --prefix apps/web run build` | 通过 | TypeScript 通过，Vite 转换 42 个模块，最终构建 711 ms |
| `node --check apps/extension/popup.js`；通过 `node -` 在 `node:vm` 内运行 popup 源码和模拟扩展 API | 通过 | 外部 API 地址没有发请求，本机只发添加 POST，拒绝重定向，新建与重复反馈均正确 |
| 隔离 `DB_PATH`、`API_TOKEN_PATH` 后运行 `.\scripts\serve.ps1 -Provider fixture -Port 18098 -SkipBuild`；`.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18098` | 通过 | 16/16，跨域无 token 为 401，原搜索、总结、书签和 SSRF 冒烟均通过 |
| `httpx` 请求 `/api/tools/bookmarklet`、`/api/bookmarks`；请求分别带合成 Host 和跨域 token | 通过 | 原版非本机 Host 读 token 200、跨域读 200、删 204。修复后伪造 Host 403；合法 token 响应 `Cache-Control: no-store`；跨域读和删均 403，重复添加 200 且数据库记录不变 |
| HTTP 读取 `/manifest.webmanifest` 及两个图标 | 通过 | 两个文件均返回 `image/png`，头部实际尺寸分别 192×192、512×512 |
| 内置浏览器打开 `http://127.0.0.1:18099/` 的测试来源，执行同一生成函数产生的 bookmarklet 代码 | 通过 | 浏览器显示已收藏，API 实际写入 `http://127.0.0.1:18099/` 一条。对 `/blocked` 启用 `connect-src 'none'` 并模拟确认后，跳转到本机表单，自动填入测试网址和标题，库中仍为 1 条 |
| 浏览器向 `/bookmarks` 传空 `url` 和包含中文括号的 `text`，再点击「一键添加」 | 通过 | 预填得到完整 asyncio 网址与标题，未自动收藏，地址栏恢复 `/bookmarks`；工具页生成 `javascript:` 链接，390 像素下无横向溢出 |

证据为终端、HTTP 断言和浏览器状态摘要。临时服务已停止，报告未记录 token 值。

## 5 关键决策

| 决策 | 依据 |
| --- | --- |
| 一键添加 token 只能新增 | 覆盖三通道用途并避免暴露已有备注或允许读取、编辑、删除 |
| 保持仅回环访问，浏览器拦截时转本机预填 | 兼容浏览器本地网络权限和站点限制，保留用户确认。[Chrome 本地网络访问](https://developer.chrome.com/docs/modern-web-guidance/guides/security/local-network-access) |
| 同时支持 `url` 和 `text` 并提供实际尺寸图标 | Android 分享可能把网址放在文本里。安装清单需提供尺寸合适的图标。[Chrome 分享目标](https://developer.chrome.com/docs/capabilities/web-apis/web-share-target) · [清单图标要求](https://developer.chrome.com/docs/lighthouse/pwa/installable-manifest/) |

## 6 遗留与风险

- 扩展清单、弹窗运行逻辑和后端协议已验收，尚未在 Chrome 或 Edge 中实际加载未打包扩展。
- 手机端 PWA 的安装和系统分享菜单未验证；本次仅验证清单资源与相同分享入口的浏览器预填。默认服务仅监听电脑本机回环，手机须能访问自己的可用部署。
- 浏览器测试使用两个回环源，未覆盖外部 HTTPS 网页上的真实本地网络权限提示。Compose 的持久卷改动未用实际容器复验。

## 7 交接

在独立 Chrome 或 Edge 配置里加载 `apps/extension`，用本机实例验证真实弹窗收藏。随后在有可访问部署的 Android 上验证安装和系统分享。

- `README.md` 的「一键添加」记录入口、权限和运行条件。
- `docs/决策与接口变更.md` 的「M8 验收修正」记录契约和取舍。

## 8 更正 · 2026-11-06 22:24（DSH/lead）

§6 遗留第 1 条「尚未在 Chrome 或 Edge 中实际加载未打包扩展」已消化：

- 用 `scripts/verify-extension.cjs` 在真实 Chromium（Playwright 自带，`--load-extension`）加载 `apps/extension`，popup 填 token 后收藏成功、后台保存函数可用；
- `Page.getAppManifest` 解析到含 `share_target` 的清单，`Page.getInstallabilityErrors` 返回空数组；
- 证据与命令见 [M8 真实浏览器验收](completed/2026-11-06-2224-m8-real-browser-verify.md)，截图在 `docs/m9-evidence/`。

仍未验证：Edge / 正式渠道 Chrome、Android 真机安装与系统分享菜单；故本报告状态保持「部分完成」不改。

# 完工报告 · 代理关闭后浏览器直连可用性核查

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261112-1707 |
| 开始 | 2026-11-12 17:07 |
| 结束 | 2026-11-12 17:08 |
| 耗时 | 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | ops |
| 状态 | 完成 |

## 1 任务

**目标**

在用户关闭代理后，核查本机浏览器（Edge / Chrome / Playwright Chromium）走直连时的实际可用性，并确认代理是否真的不再参与链路。

**验收标准**

- 代理开关状态有可判定证据：系统代理、WinHTTP、环境变量、TUN 适配器、代理端口客户连接。
- 浏览器直连出口 IP 与运营商可读出，且不是境外代理出口。
- 三种浏览器各自对同一批站点给出成功/失败记录（含状态码、耗时、标题）。
- 本地应用在无代理浏览器里能正常打开并出结果。

**不做**

- 不改 Clash 配置、不动代理节点；不重开代理。
- 不评估真实 SearXNG 模式（本机 8888 未运行），只用 fixture 验证浏览器链路。
- 不做引擎工程质量评估，只记录直连可达性。

## 2 做了什么

1. 采集代理状态 → 系统代理 / WinHTTP / 环境变量 / TUN / 代理端口 → 结论：系统层已关，mihomo 内核仍在监听 7897。
2. 用 curl 取直连出口 IP → `ip.3322.net`、`myip.ipip.net`、`ipinfo.io/ip`、`ifconfig.me` → 一致为 `111.15.79.78`（中国山东烟台 移动）。
3. 三种浏览器以 `--no-proxy-server` 无头运行 → Chrome 157、Edge 157、Playwright Chromium 156，逐站记录状态码/耗时/标题。
4. 浏览器内再取一次出口 IP（`http://ip.3322.net`、`https://myip.ipip.net`）→ 与 curl 相同，确认浏览器没有偷偷走代理。
5. 以 curl 对 19 个项目在用搜索引擎入口做直连矩阵（每站最多 2 次、单次 6s）。
6. 起本地服务 `serve.ps1 -Provider fixture`，用无代理 Playwright 打开 `http://127.0.0.1:8000/` 并执行一次检索，截图留证。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `reports/assets/proxy-off-browser/browser-direct.json` | 新增 | 三浏览器直连结果（Playwright 版） |
| `reports/assets/proxy-off-browser/browser-direct-engines.json` | 新增 | 追加站点直连结果 |
| `reports/assets/proxy-off-browser/local-browser.json` | 新增 | 本地应用浏览器验收 |
| `reports/assets/proxy-off-browser/local-home.png` | 新增 | 首页截图 |
| `reports/assets/proxy-off-browser/local-search.png` | 新增 | 检索结果页截图 |
| `reports/2026-11-12-1707-proxy-off-browser.md` | 新增 | 本报告 |
| `reports/INDEX.md` | 修改 | 台账自动插入一行 |

临时探测脚本放在 `.tmp-probe/`（`probe-proxy.ps1`、`probe-net.ps1`、`probe-net2.ps1`、`probe-clash.ps1`、`probe-env.ps1`、`probe-engines.ps1`、`browser-direct.cjs`、`browser-engines.cjs`、`local-browser.cjs`），收尾后删除。

## 4 验证与证据

**代理状态（系统层已关，内核未退）**

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 环境变量 | `Get-ChildItem Env: \| ? Name -match proxy` | 无任何 `*_PROXY`，Playwright 进程内亦为 null |
| 系统代理 | `HKCU:\...\Internet Settings` | `ProxyEnable=0`，`ProxyServer=127.0.0.1:7897`（残留字段，未启用） |
| WinHTTP | `netsh winhttp show proxy` | Direct access (no proxy server) |
| TUN 适配器 | `Get-NetAdapter` | 无 wintun/tap 设备；默认路由走 WLAN（172.18.255.254） |
| Clash 配置 | `%APPDATA%\io.github.clash-verge-rev.clash-verge-rev\verge.yaml` | `enable_tun_mode: false`、`enable_system_proxy: false`、`enable_dns_settings: false` |
| 代理端口 | `Get-NetTCPConnection -RemotePort 7897` | 无客户端连接；但 `verge-mihomo` (pid 20680) 仍 Listen 127.0.0.1:7897 |
| 代理端口可用性 | `curl -x http://127.0.0.1:7897 https://www.google.com` | `302`，2.37s —— 内核没退，显式指定代理仍能出去 |

浏览器进程：Edge 157 在跑（真实浏览器 + webview2，命令行无 `--proxy-server`），Chrome 未运行，Playwright Chromium 156.0.8078.4 可用（`ms-playwright\chromium-1248\chrome-win64\chrome.exe`）。Chrome/Edge 均无代理组策略（`HKLM/HKCU Policies` 不存在）。

**直连出口（含浏览器内）**

| 来源 | 结果 |
| --- | --- |
| `curl --noproxy "*" http://ip.3322.net` | 111.15.79.78 |
| `curl https://myip.ipip.net` | 当前 IP：111.15.79.78 来自于：中国 山东 烟台 移动 |
| `curl https://ipinfo.io/ip` / `ifconfig.me/ip` | 111.15.79.78 |
| 浏览器内 `page.goto("http://ip.3322.net")` | body = 111.15.79.78 |
| 浏览器内 `page.goto("https://myip.ipip.net")` | body = 当前 IP：111.15.79.78 来自于：中国 山东 烟台 移动 |

**浏览器直连矩阵（`--no-proxy-server`，无头）**

| 浏览器 | 站点 | 结果 | 耗时 | 1 分钟 |
| --- | --- | --- | --- | --- |
| Chrome 157 | https://www.baidu.com | 200 | — | 百度一下，你就知道 |
| Chrome 157 | https://www.bing.com | 200 | — | 搜索 - Microsoft 必应 |
| Chrome 157 | https://github.com | 超时 >28s | — | dump-dom 未返回 |
| Chrome 157 | https://api.ipify.org | Page load failed | — | 页面未加载 |
| Chrome 157 | https://www.google.com | Page load failed | — | 页面未加载 |
| Chrome 157 | http://127.0.0.1:58808/ | 401 | — | DSH Web 需重开带令牌 URL（预期） |
| Edge 157 | https://www.baidu.com | 200 | — | 百度一下，你就知道 |
| Edge 157 | https://www.google.com | Page load failed | — | 页面未加载 |
| Edge 157 | http://127.0.0.1:58808/ | 401 | — | 同上 |
| Playwright Chromium 156 | baidu / bing | 200 / 200 | 552ms / 982ms | 正文正常 |
| Playwright Chromium 156 | ip.3322.net / myip.ipip.net | 200 / 200 | 84ms / 533ms | 出口 IP 正确 |
| Playwright Chromium 156 | github / google | 超时 20s | 20028ms / 20003ms | goto 超时，无 requestfailed（TCP/TLS 阶段被断） |
| Playwright Chromium 156 | sogou / so.com | 200 / 200 | 473ms / 727ms | 搜狗搜索 / test_360搜索 |
| Playwright Chromium 156 | yandex.com | 200 | 8700ms | 标题 “Are you not a robot?”（反爬验证页） |
| Playwright Chromium 156 | swisscows.com | 200 | 2782ms | Web pages for test - Swisscows |
| Playwright Chromium 156 | zh.wikipedia.org / duckduckgo.com | 超时 12s | 12013ms / 12008ms | 不可达 |

**搜索引擎入口直连矩阵（curl，`--noproxy "*"`，最多 2 次 × 6s）**

| 结果 | 入口 |
| --- | --- |
| 可达 | `cn.bing.com` 200 / 0.42s、`www.so.com` 200 / 0.75s、`www.sogou.com` 302 / 0.33s、`search.naver.com` 200 / 2.20s、`yandex.com` 302 / 2.11s、`swisscows.com` 200 / 4.00s、`export.arxiv.org` 301 / 0.53s |
| 不可达 | `www.google.com`、`cse.google.com`、`html.duckduckgo.com`、`duckduckgo.com`、`search.brave.com`、`www.youtube.com`、`github.com`、`scholar.google.com`、`zh.wikipedia.org`、`www.startpage.com`、`www.mojeek.com`、`search.yahoo.com`（全部 `000`，6s 内无握手） |
| 不稳定 | `github.com`：16:58 首次 `curl -4` 返回 200 / 1.15s，17:03 复测 `000` / 10s，随后浏览器亦超时 —— 直连成功率随机 |

DNS 侧证据：`hosts` 无自定义条目；`www.google.com` 解析为 `185.45.5.35`、AAAA `2001::1`（非 Google 地址，属污染/劫持应答）；WLAN 已禁用 IPv6，仅存 Teredo 伪接口，不影响上述结论。

**本地应用（无代理浏览器）**

| 步骤 | 命令 / 动作 | 结果 |
| --- | --- | --- |
| 起服务 | `scripts/serve.ps1 -Provider fixture` | `/api/health` = `{"status":"ok","provider":"fixture","web_built":true,...}` |
| 首页 | `page.goto("http://127.0.0.1:8000/")` | 200，标题 `CleanSearch` |
| 检索 | 输入框填 `test` + Enter | URL `/?q=test`，渲染 8 条结果，meta 显示「固定样本 展示 8 条 / 上游 11 · 去重 1 · 0 ms」，引擎 google/brave/bing/duckduckgo |
| 直连接口（探测口误） | `POST /api/search {"q":"test","opts":{"fixture":true}}` | 422：`fixture` 只接受 `hit/empty/error/risky`；改为不带 `opts` 的 `{"q":"test"}` 后 200，返回完整 groups |

证据文件：

- [browser-direct.json](../assets/proxy-off-browser/browser-direct.json)
- [browser-direct-engines.json](../assets/proxy-off-browser/browser-direct-engines.json)
- [local-browser.json](../assets/proxy-off-browser/local-browser.json)
- [local-home.png](../assets/proxy-off-browser/local-home.png)
- [local-search.png](../assets/proxy-off-browser/local-search.png)

未验证：

- 真实 SearXNG 模式（`127.0.0.1:8888` 未运行）在无代理下能否出结果 —— 需起 SearXNG 后跑 `POST /api/search` 真实分支。
- 已在运行的 Edge 交互式会话（有窗口那个进程）未做页面级抓取，只核对了命令行与系统代理继承关系。
- 未测移动端/Android 验收脚本在无代理下的表现。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 用 `--no-proxy-server` 显式禁止浏览器代理，而不是依赖系统代理为 0 | 直接沿用系统设置 | 若系统或扩展残留代理，结果会被掩盖；显式开关能证明「浏览器真的在直连」 |
| 以浏览器内出口 IP 作为「没走代理」的硬判据 | 只看环境变量和注册表 | 出口 IP 落在国内移动网段，才能排除 TUN/透明代理 |
| 引擎可达性用 curl 矩阵，浏览器只抽样 | 全部站点都开浏览器 | 浏览器超时挂 20s/站，19 站不可行；curl 6s 足够区分「连不上」和「慢」 |
| 本地应用用 fixture 验收 | 起 SearXNG 真实模式 | 本次只验浏览器链路，fixture 足够且不受海外引擎不通干扰 |

## 6 遗留与风险

- **代理只是系统层关了**：`verge-mihomo` 仍在监听 `127.0.0.1:7897`，显式 `-x` 仍可翻墙。任何配置里写死该代理的工具（含旧脚本、扩展、镜像加速配置）仍会走代理，这会让「非代理」结论对它们不成立。
- **直连能力缺口明显**：Google 全家、DuckDuckGo、Brave、YouTube、Wikipedia、Startpage、Mojeek、Yahoo、GitHub 全部不可达；项目 19 个引擎里约 12 个在无代理下拿不到结果。
- **GitHub 直连不稳定**：同一小时内出现 200 / 000 两种结果，浏览器只会表现为长时间白屏，不是可靠判据。
- **DNS 被污染**：`www.google.com` 返回 `185.45.5.35` 与 `2001::1`，无代理时任何依赖域名解析的浏览器测试都会被误导。
- **DSH Web GUI 无法直接验证**：`http://127.0.0.1:58808/` 返回 401，需要带 `dsh web` 打印的令牌 URL，本轮未取令牌。
- 未清理的临时脚本 `.tmp-probe/`（本报告收尾时删除，若仍存在属遗漏）。

## 7 交接

**下一个人第一件事**

要恢复完整检索能力，把 Clash Verge 的系统代理重新打开（UI 开关，或 `verge.yaml` 置 `enable_system_proxy: true` 后重启内核）；只想在无代理下验收，就把 SearXNG 引擎集限制到 `bing/sogou/360search/naver/yandex/swisscows/arxiv`。

**相关文件**

- 证据目录：`reports/assets/proxy-off-browser/`
- 引擎目录真源：`apps/api/app/core/engine_catalog.py`
- 浏览器验收辅助：`scripts/browser-check.cjs`
- 启动服务：`scripts/serve.ps1`

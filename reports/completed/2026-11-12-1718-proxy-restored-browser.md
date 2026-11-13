# 完工报告 · 代理恢复后浏览器功能回归

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261112-1718 |
| 开始 | 2026-11-12 17:17 |
| 结束 | 2026-11-12 17:18 |
| 耗时 | 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | ops |
| 状态 | 完成 |

## 1 任务

**目标**

用户重新打开代理后，把浏览器链路恢复到可用状态：确认代理实际生效方式、清掉无代理期间留下的 DNS/进程残留、逐站复验 Edge / Chrome / Playwright Chromium，并确认本地应用仍可在浏览器里正常用。

**验收标准**

- 能说清「代理是怎么生效的」：系统代理 / TUN / 出口节点与出口 IP。
- 无代理期间解析到的污染地址与残留无头进程已清理。
- 浏览器对关键站点给出 200 与耗时记录，失败项能定位到站点反爬而不是本机配置。
- 本地 `127.0.0.1:8000` 首页与检索在浏览器中正常。

**不做**

- 不改 Clash 规则、不换节点、不动用户正在使用的 Edge 窗口。
- 不验证真实 SearXNG 模式的引擎质量（只记可达性）。
- 不重装浏览器、不清空用户浏览器配置。

## 2 做了什么

1. 读代理真实状态 → 发现生效方式是 **TUN（`Mihomo Meta Tunnel` 已 Up）**，不是系统代理；`enable_system_proxy` 仍为 false。
2. 取两条出口：显式走 7897 的境外出口、按规则直连的国内出口。
3. 清残留：`Clear-DnsClientCache` 清本地 DNS 缓存；扫描并清理上次遗留的无头 Chrome。
4. 用 Playwright Chromium 156 复验 10 个站点（不传 `--no-proxy-server`，浏览器按系统设置直连、真实流量由 TUN 接管）。
5. 抓运行中 Edge 的已建立连接，确认它的新流量已进 fake-ip（198.18.x / 2001:2::x），即已在走代理。
6. 起 `serve.ps1 -Provider fixture`（端口已被上一轮实例占用，实际复用 pid 7308），用浏览器跑首页 + 检索 + 截图。
7. 单独诊断 Google 搜索页，确认是出口 IP 触发 `/sorry` 验证码而非浏览器故障。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `reports/assets/proxy-restored-browser/browser-restored.json` | 新增 | 10 站浏览器复验结果 |
| `reports/assets/proxy-restored-browser/local-browser-restored.json` | 新增 | 本地应用浏览器验收 |
| `reports/assets/proxy-restored-browser/local-search-restored.png` | 新增 | 本地检索页截图 |
| `reports/assets/proxy-restored-browser/google-search.png` | 新增 | Google 搜索页空白/拦截截图 |
| `reports/2026-11-12-1718-proxy-restored-browser.md` | 新增 | 本报告 |
| `reports/INDEX.md` | 修改 | 台账自动插入一行 |

系统侧只做了无损操作：清 DNS 客户端缓存、结束遗留无头 Chrome（无 UI 进程）。未改注册表、未改 Clash 配置、未重启用户的 Edge。

## 4 验证与证据

**代理生效方式**

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 系统代理 | `HKCU:\...\Internet Settings` | `ProxyEnable=0`（仍未启用） |
| Clash 开关 | `verge.yaml` | `enable_tun_mode: true`、`enable_system_proxy: false`、`enable_dns_settings: false` |
| TUN 网卡 | `Get-NetAdapter` | `Mihomo Meta Tunnel` = Up（ifIndex 14） |
| 默认路由 | `Get-NetRoute 0.0.0.0/0` / `::/0` | IPv4 经 `198.18.0.2`（Mihomo）、IPv6 经 `fdfe:dcba:9876::2`（Mihomo），metric 0 |
| 代理端口 | `Get-NetTCPConnection -LocalPort 7897` | verge-mihomo (pid 20680) 仍 Listen 127.0.0.1:7897 |
| 境外出口 | `curl -x http://127.0.0.1:7897 http://ip-api.com/json` | Japan / Tokyo / G-Core Labs / AS199524 / `85.234.83.168` |
| 国内直连出口 | `curl https://myip.ipip.net`（走规则直连） | 223.104.195.35 中国山东烟台 移动 |

**清理与残留**

| 动作 | 结果 |
| --- | --- |
| `Clear-DnsClientCache` | cleared；`www.google.com` 现解析为 `198.18.0.140`（fake-ip，不再是 185.45.5.35） |
| 遗留无头 Chrome | 无（上一轮已随进程退出回收） |
| `ipconfig /flushdns` | 需要提权，被拒；已用非特权 `Clear-DnsClientCache` 替代 |
| 运行中 Edge | 已建立连接指向 `2001:2::6`、`2001:2::42`、`198.18.1.61:443`，说明现有窗口的新流量已进 TUN |

**浏览器复验（Playwright Chromium 156.0.8078.4，无代理参数，TUN 承载）**

| 站点 | 状态 | 完成 | 1 分钟 |
| --- | --- | --- | --- |
| https://www.google.com | 200 | 10.0s | Google（首屏正常） |
| https://github.com | 200 | 3.7s | GitHub · Change is constant… |
| https://duckduckgo.com/?q=test | 200 | 3.5s | DuckDuckGo |
| https://www.youtube.com | 200 | 8.4s | YouTube |
| https://zh.wikipedia.org/wiki/Wikipedia | 200 | 2.7s | 维基百科 - 自由的百科全书 |
| https://www.baidu.com | 200 | 1.2s | 百度一下，你就知道 |
| https://www.bing.com | 200 | 0.65s | 搜索 - Microsoft 必应 |
| https://search.brave.com/search?q=test | 429 | 12.6s | Captcha - Brave Search（站点反爬，非本机） |
| https://www.startpage.com/sp/search?query=test | 200 | 4.8s | 页面标题 Access Denied（PoW 拦截） |
| https://www.mojeek.com/search?q=test | 403 | 2.3s | 403 - Forbidden |

**Google 搜索页单独诊断**

| 步骤 | 结果 |
| --- | --- |
| `curl https://www.google.com/search?q=test` | 302 / 1.24s |
| 浏览器 `goto(..., waitUntil: commit)` | 302 → google.com.hk → 302 → `429 https://www.google.com/sorry/index?...` |
| 页面正文 | “我们的系统检测到您的计算机网络中存在异常流量…IP 地址：85.234.83.168” |
| 结论 | 出口节点 IP 被 Google 判为异常流量，需换节点或过验证码；浏览器本身链路正常 |

**本地应用**

| 步骤 | 结果 |
| --- | --- |
| `curl /api/health` | 200，`provider=fixture`、`web_built=true` |
| 首页 | 200，标题 `CleanSearch` |
| 检索 `test` | URL `/?q=test`，渲染 8 张结果卡，控制台仅 2 个静态资源 404（favicon 类） |

证据文件：

- [browser-restored.json](../assets/proxy-restored-browser/browser-restored.json)
- [local-browser-restored.json](../assets/proxy-restored-browser/local-browser-restored.json)
- [local-search-restored.png](../assets/proxy-restored-browser/local-search-restored.png)
- [google-search.png](../assets/proxy-restored-browser/google-search.png)

未验证：

- 用户正在使用的 Edge 窗口内页面是否已刷新——只能从连接层证明走代理，不能证明旧标签页已重载。
- 真实 SearXNG 模式下 19 个引擎的恢复率——需起 8888 后跑真实分支。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 不重开系统代理，沿用 TUN | 把 `enable_system_proxy` 改成 true | 用户已开 TUN，全局透明接管，浏览器无需任何代理设置；再开系统代理会多一层，排障时反而分不清 |
| 浏览器测试不传 `--no-proxy-server` | 继续用显式直连参数 | 本轮要验证的是「真实浏览器现状」，显式禁用代理会绕过 TUN 的接管判断 |
| 用 `Clear-DnsClientCache` 代替 `ipconfig /flushdns` | 提权跑 flushdns | 前者不需提权且效果等价；提权弹窗会打断用户 |
| 不动用户的 Edge 进程 | 重启 Edge 强制清缓存 | 重启会丢标签页；TUN 已接管，刷新即可 |
| 复用已在跑的 8000 实例 | 杀掉后重启 | 端口被上一轮 python 进程占用，实例健康且为当前代码构建，无必要打扰 |

## 6 遗留与风险

- **系统代理仍是关的**：只靠 TUN 生效。任何绕过 TUN 的程序（绑定物理网卡、自建 socket 绕过路由、Docker/WSL 特殊网络）不会走代理；系统级工具（如 WinHTTP 客户端）仍按直连处理。
- **引擎侧仍有三道墙**：Brave 429 Captcha、Startpage Access Denied、Mojeek 403，与本机浏览器无关，SearXNG 侧同样会吃这些失败。
- **Google 搜索需要过验证码**：出口 `85.234.83.168` 已被 Google 标记；换节点可缓解。
- **WLAN 网关变了**：默认路由下一跳从 `172.18.255.254` 变成 `192.168.43.1`，像是切到了手机热点；若之后出现间歇性断流，先查这里。
- **8000 端口有 orphan 实例**：pid 7308（17:07 起，fixture），本轮复用未重启；需要干净状态时先停它再 `serve.ps1`。

## 7 交接

**下一个人第一件事**

浏览器已可用；要跑真实引擎验收，先停掉 pid 7308 的旧实例，起 SearXNG（8888）后按 `docs/进展与欠账.md` 的在线矩阵复跑，重点看 Brave/Startpage/Mojeek 是否仍被反爬拦截。

**相关文件**

- 证据目录：`reports/assets/proxy-restored-browser/`
- 上一轮无代理核查：`reports/completed/2026-11-12-1707-proxy-off-browser.md`
- 启动服务：`scripts/serve.ps1`
- 引擎目录：`apps/api/app/core/engine_catalog.py`

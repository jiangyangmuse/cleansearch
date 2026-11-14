# 完工报告 · 免安装分发包（PyInstaller）

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261114-1939 |
| 开始 | 2026-11-14 19:39 |
| 结束 | 2026-11-14 19:39 |
| 耗时 | 不到 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

**目标**

做一个能下载到别的电脑直接用的包：`scripts/build-portable.ps1` 一键产出 Windows x64 免安装 zip，目标机器不需要 Python / Node / Docker。对应 [backlog 的「桌面与扩展分发」](../backlog/README.md)。

**验收标准**

- 产出一个 zip，解压后可运行，`/api/health` 返回 `api_version=2` 与五项能力全 true。
- 包内自带前端产物、固定样本、schema 与提示词；`data/` 是唯一可变状态。
- 在**仓库之外的目录**（`%TEMP%`）运行同样通过：冒烟 16/16、浏览器审计 312/312。
- README 有分发说明；`.gitignore` 排除构建产物。

**不做**

- 不做 Tauri 桌面壳、应用商店分发（backlog 仍保留）。
- 不做自动更新、代码签名（Windows SmartScreen 会对未签名 exe 提示）。
- 不把 `dist-portable/` 提交进仓库（zip 走发布页/网盘传递）。

## 2 做了什么

1. `packaging/launcher.py`：发行入口。import `app` 之前把 `WEB_DIST`/`DB_PATH`/`API_TOKEN_PATH`/`FAVICON_DIR`/`BLOCKLIST_PATH`/`FEED_OUTPUT_PATH` 指向 exe 同目录，默认 `SEARCH_PROVIDER=fixture`、`UVICORN_LOOP=asyncio`、端口被占用自动换空闲端口、可选自动开浏览器。
2. `scripts/build-portable.ps1`：构建前端 → PyInstaller `--onedir` → 拷 `web/`、`resources/blocklist.txt` → 生成 `启动 CleanSearch.bat` 与 `说明.txt` → 打 zip。
3. 踩了两个打包专属坑并修掉：`_free_port` 把 `bind` 写成两个参数（打包后立刻崩）；`schema.sql` 与 fixtures 不是 `.py`，PyInstaller 不会自动收集——缺 schema 时 `/api/bookmarks` 500、缺 fixtures 时 fixture 模式 503。
4. 校验「换台电脑」：把 zip 解压到 `%TEMP%\cleansearch-portable-test` 运行，健康检查、搜索、冒烟全过。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `packaging/launcher.py` | 新增 | 发行入口：相对路径、默认配置、自动端口、可选开浏览器 |
| `scripts/build-portable.ps1` | 新增 | 一键构建：前端 → PyInstaller → 资源 → bat/说明 → zip |
| `README.md` | 修改 | 新增「分发给别的电脑（免安装包）」小节 |
| `.gitignore` | 修改 | 排除 `build-portable/`、`dist-portable/` |
| `docs/决策与接口变更.md` | 修改 | 记录分发包形态、必须随包的数据与边界 |
| `reports/backlog/README.md` | 修改 | 「桌面与扩展分发」标注免安装 zip 已交付 |
| `reports/assets/portable-package/` | 新增 | 打包版审计日志、冒烟日志、截图 |

产物（不入库）：`dist-portable/CleanSearch-0.1.0-win-x64.zip` — **53.5 MB**，解压后 2,505 个文件 / 117 MB。

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `.\scripts\build-portable.ps1` | 通过 | 前端构建 + PyInstaller + zip，约 60 秒 |
| `& dist-portable\CleanSearch\CleanSearch.exe`（`API_PORT=18080`） | 通过 | health `api_version=2`、五项能力全 `true`、`web_dist`/`db_path` 都在包内 |
| `pwsh scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18080` | 通过 | `冒烟通过 16/16，跳过 0`（[日志](../assets/portable-package/smoke.log)） |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18080` | 通过 | **`ALL PASS (312)`**（[明细](../assets/portable-package/audit.log)） |
| 解压到 `%TEMP%\cleansearch-portable-test` 后运行（`API_PORT=18081`） | 通过 | 在仓库之外运行：health OK、`POST /api/search` 10 条 + 3 条官方、冒烟 16/16 |

打包版实测端口与产物：`18080`（仓库内目录）、`18081`（%TEMP% 解压副本），两次都未污染日常 8000。

未验证：Windows 10 与杀软/SmartScreen 的实际拦截提示（本轮只在当前机器 Win11 跑）；macOS/Linux 发行版未做；真实 SearXNG 模式在包内未跑（需要外部 SearXNG，配置方式写进说明.txt）。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| PyInstaller `--onedir` + zip | 单文件 `--onefile` | 单文件每次启动要解压到临时目录，首次启动慢 3–5 秒且杀软更容易误杀；目录形式便于增量替换 `web/`、`data/` |
| 默认 `fixture` 模式 | 默认连 SearXNG | 分发对象不该被迫先装 Docker；固定样本能让界面完整可用，真搜索按需配置 |
| 环境变量设置放在 import `app` 之前 | 用配置文件 | `app.config` 在 import 时读环境变量；配置文件还得再加一层解析，没必要 |
| 不打包 `.env` | 打进去 | 里面是个人密钥与路径，打进去等于把本机配置发给别人 |

## 6 遗留与风险

- exe 未签名：Windows 首次运行会有 SmartScreen「未知发布者」提示；要消除需代码签名证书。
- 包体 117 MB（zip 53.5 MB），主要是 trafilatura/lxml 与 Python 运行时；若只发固定样本模式，可去掉 trafilatura 再瘦身。
- 打包版没有自动更新；升级靠覆盖 `CleanSearch.exe`、`web\`、`resources\`，保留 `data\`。
- 只验证了当前机器（Win11 x64）；未测 Win10、老 CPU、非 ASCII 用户名路径下的 DB 写入（本轮用的是 %TEMP%，路径含用户名但纯 ASCII）。

## 7 交接

**下一个人第一件事**

要发到别的机器：把 `dist-portable/CleanSearch-0.1.0-win-x64.zip` 传过去即可；若想让真实搜索可用，先在那台机器（或另一台）跑 SearXNG，再按 `说明.txt` 加两个环境变量。

**相关文件**

- 打包：`packaging/launcher.py`、`scripts/build-portable.ps1`
- 说明：`README.md` §6、`docs/决策与接口变更.md`（2026-11-14 免安装分发包）
- 证据：`reports/assets/portable-package/`
## 8 追加轮次 2026-11-14 19:55（内置 SearXNG 与发布）

**目标**：让包开箱就能真搜索——随包带一个 SearXNG 的 compose，一键起停。

**做了什么**

1. `packaging/searxng/{docker-compose.yml,settings.yml}`：镜像 `searxng/searxng:latest`，容器名 `cleansearch-searxng`，只绑 `127.0.0.1:8891`（不与仓库自用的 `cs-searxng:8888` 冲突）。
2. 包内新增 `启动 CleanSearch（真实搜索）.bat` 与 `停止 SearXNG.bat`：前者 `docker compose up -d` + 设 `SEARCH_PROVIDER=searxng`/`SEARXNG_URL`/`SEARXNG_WAIT=1` 后启动 exe；后者 `down`。
3. 等上游就绪的逻辑放进 `launcher.py`（`SEARXNG_WAIT=1` 时轮询 `/search?q=test&format=json`，最多 150 秒），bat 里不写循环——首版在 bat 里写 PowerShell 单行把引号写坏，脚本直接解析失败（用 `Parser::ParseFile` 才定位到）。
4. 精简版 settings 只有 `use_default_settings`，实测 `site:` 查询把可用引擎逼到 0 个、返回 503；改成仓库同源配置（bing 走 `cn.bing.com`、mojeek/swisscows 显式激活等）后恢复正常。

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `docker compose -f searxng/docker-compose.yml up -d`（包内） | 通过 | `cleansearch-searxng` 起在 `127.0.0.1:8891`，`/search?q=python&format=json` 200 / 51 条 |
| `CleanSearch.exe`（`SEARCH_PROVIDER=searxng`、`SEARXNG_WAIT=1`、端口 18083） | 通过 | 日志 `等待 SearXNG 就绪… SearXNG 已就绪，开始真实搜索模式`；health `provider=searxng` |
| `node scripts/verify-filters.cjs http://127.0.0.1:18083` | 通过 | **`ALL PASS (9)`**：站点仅 `docs.python.org`、周 18 条、语言 18 条、严格去重 17 条无重复标题、关闭去重 `dup=0`、缓存命中（[日志](../assets/portable-package/verify-filters-real.log)） |
| `.\scripts\build-portable.ps1 -SkipWebBuild` | 通过 | 重新打包：`dist-portable/CleanSearch-0.1.0-win-x64.zip`（53.5 MB），包内含 `searxng/` 与三个 bat |
| `Get-ChildItem dist-portable/CleanSearch` | 通过 | `_internal data resources searxng web CleanSearch.exe 启动 CleanSearch.bat 启动 CleanSearch（真实搜索）.bat 停止 SearXNG.bat 说明.txt` |

**边界与遗留**：包内 SearXNG 冷启动时引擎要预热，前几次查询可能 503（`launcher` 的等待只保证 HTTP 可达，不保证引擎都有结果）；引擎可用性仍取决于对方网络。未验证：目标机器没装 Docker 时脚本的提示路径。
## 9 追加轮次 2026-11-14 20:50（桌面快捷方式）

**目标**：双击桌面图标就能用；重复双击不要起第二个实例。

**做了什么**

1. `scripts/create-shortcut.ps1`：生成桌面 `.lnk`（目标/工作目录/图标显式写入），图标由 `web/icon-192.png` 现场包成 ICO（内嵌 PNG，无需额外工具）。
2. 包内新增 `创建桌面快捷方式.bat` + `tools/create-shortcut.ps1`，别的电脑解压后也能一键建快捷方式。
3. `launcher.py` 改为「已在运行就只开浏览器」：先探 `API_PORT` 的 `/api/health`，命中则开浏览器并退出；端口被占用时按 `8000 → 8001…8010` 顺序挑。首版用 `response.read(200)` 只读 200 字节，JSON 被截断导致探测永远失败（表现为又起了个 8001 实例），改为整段读取。
4. 把日常 `data/cs.db` 用 SQLite backup API 复制进包内 `data\`，令牌一并复制，快捷方式启动的实例与日常书签一致。

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `pwsh scripts\create-shortcut.ps1 -Target dist-portable\CleanSearch\CleanSearch.exe -Name CleanSearch` | 通过 | `C:\Users\HUAWEI\OneDrive\Desktop\CleanSearch.lnk`；target/workdir/icon 三项已回读确认，`CleanSearch.ico` 生成成功 |
| 8000 已被日常实例占用时直接跑 exe（`CLEANSEARCH_NO_BROWSER=1`） | 通过 | 输出「检测到 http://127.0.0.1:8000/ 已在运行，直接打开浏览器」，`EXIT=0`，无残留进程 |
| `API_PORT=18090` 跑 exe | 通过 | 正常起服务：`/api/health` → `provider=fixture`、`db_path=...\dist-portable\CleanSearch\data\cs.db`、`bookmarks=1`、`api_version=2` |
| `.\scripts\build-portable.ps1 -SkipWebBuild` | 通过 | 包内新增 `tools/`、`创建桌面快捷方式.bat`；zip 53.5 MB |
| 重新上传 v0.1.0 asset | 通过 | 删除旧 asset `747190483` 后上传新包，下载地址不变，size=53.5 MB |

**边界**：快捷方式指向 `dist-portable\CleanSearch\`，该目录在 `.gitignore` 里、重建会清空——重建后需重新执行一次 `create-shortcut.ps1`（包内 bat 也行）。图标只有 192px 一档，高分屏字号下略糊。
## 10 追加轮次 2026-11-14 20:58（二次复查 R-13…R-18 修复）

来源：[二次复查报告](./2026-11-14-2036-portable-recheck.md) 与方案 §8。逐条处理：

| 编号 | 级别 | 处理 | 落点 |
| --- | --- | --- | --- |
| R-13 | P1 | launcher 改成 `uvicorn.run(host=API_HOST)`，非回环时打印提醒；`说明.txt` 改口径：手机访问要同时设 `API_HOST=0.0.0.0` + `ALLOWED_HOSTS` 并放行防火墙 | `packaging/launcher.py`、`scripts/build-portable.ps1` 的说明文案 |
| R-14 | P2 | compose 镜像钉 digest `sha256:c750ee1d…`，不再用 `latest` | `packaging/searxng/docker-compose.yml` |
| R-15 | P2 | 横幅文案不再写死在仓库里才有的 `scripts\\serve.ps1` 路径，改成「免安装版重新双击 / 源码版跑 serve.ps1」 | `apps/web/src/components/ServerBanner.tsx` |
| R-16 | P3 | `说明.txt` 去掉「中文路径也可以」的断言（改为建议纯英文、中文未测）；README 的审计数字对齐当前口径 | 构建脚本说明、README |
| R-17 | P3 | `outdated` 分支补「重试连接」按钮（与 `offline` 一致） | `ServerBanner.tsx` |
| R-18 | P3 | 开浏览器改成轮询端口真的应答后再开（最多 30 秒），不再固定 2 秒 | `packaging/launcher.py` |

验证：

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `npm --prefix apps/web run build` | 通过 | 含横幅文案改动 |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18092`（打包版，新前端） | 通过 | **`ALL PASS (308)`**（默认口径省 3 项写书签）（[日志](../assets/portable-package/audit2.log)） |
| `.\scripts\build-portable.ps1` | 通过 | 重新打包，zip 53.5 MB；随后重新播种 `data/cs.db` 与令牌、刷新桌面快捷方式 |
| 重新上传 v0.1.0 asset | 通过 | 删除旧 asset 后上传新包，下载地址不变 |

仍未处理：R-13 只改了代码与文案，**没有实测**从包里开 `API_HOST=0.0.0.0` 的手机访问（缺第二台设备）；镜像 digest 升级流程未定义。

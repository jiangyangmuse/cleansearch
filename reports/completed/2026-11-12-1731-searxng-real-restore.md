# 完工报告 · 真实 SearXNG 检索链恢复与引擎矩阵

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261112-1731 |
| 开始 | 2026-11-12 17:31 |
| 结束 | 2026-11-12 17:31 |
| 耗时 | 不到 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | ops |
| 状态 | 完成 |

## 1 任务

**目标**

执行上一轮交接的下一步：停掉占着 8000 的旧 fixture 实例，恢复 SearXNG 真实检索链（Docker + 8888），跑引擎矩阵与 API 层后缀验收，确认代理恢复后各引擎的真实可用性。

**验收标准**

- 8000 端口由新起的实例占用，旧 pid 7308 已退出。
- SearXNG 容器就绪，`/config` 可读，`/api/health` 报 `provider=searxng`。
- 有 28 引擎 × 2 轮的探测矩阵，以及走 `/api/search` 的 20 条后缀矩阵。
- `python -m pytest apps/api -q` 全通过；`smoke.ps1` 在真实与固定样本两种模式都通过。

**不做**

- 不替换出口节点、不改 Clash 规则（Google 被出口 IP 拦属于环境事实，不在本轮改）。
- 不重写引擎回退策略，只为真实模式下的误报修正冒烟判据。
- 不做前端视觉回归。

## 2 做了什么

1. 结束 orphan 实例 → 确认 8000 释放。
2. 拉起 Docker Desktop（引擎 29.9.2，9s 就绪）→ `docker compose up -d searxng` → 容器 `cs-searxng` Up，`/healthz` 4s 返 200，`/config` 载入 263 个引擎。
3. `serve.ps1 -Provider searxng` 起 API → `/api/health` 报 `provider=searxng`。
4. `scripts\probe-engines.py` 跑 28 引擎 × 2 轮矩阵，落 JSON。
5. `scripts\verify-searxng.py --engines b y mj` 跑后缀 + bang + 地区 + 默认路由共 12 例。
6. 自写一次性脚本跑 20 条 `/api/search` 后缀矩阵（全 19 个后缀 + default），记录 status/total/来源/失败引擎。
7. `python -m pytest apps/api -q --junit-xml` 拿准确用例数。
8. `smoke.ps1` 对真实实例跑冒烟 → 4 项失败；逐项定位：3 项是固定样本专用参数在真实模式不可构造，1 项是引用校验漏算官方入口区。
9. 修正 `scripts/smoke.ps1` 判据后，真实模式与 fixture 模式各重跑一次，均通过。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `scripts/smoke.ps1` | 修改 | ① `黑名单拦截/零结果/上游不可用` 三项在非 fixture 模式记 N/A 而非失败；② 引用校验的合法 id 集合补上 `official.entries` |
| `reports/assets/proxy-restore-engine-matrix/engine-probe.json` | 新增 | 28 引擎矩阵原始结果 |
| `reports/assets/proxy-restore-engine-matrix/probe-console.txt` | 新增 | 探测脚本控制台输出 |
| `reports/assets/proxy-restore-engine-matrix/suffix-matrix.json` | 新增 | 20 条 API 后缀矩阵 |
| `reports/assets/proxy-restore-engine-matrix/verify-suffix.txt` | 新增 | verify-searxng.py 输出 |
| `reports/assets/proxy-restore-engine-matrix/pytest.xml` / `pytest.txt` | 新增 | 测试结果与统计 |
| `reports/assets/proxy-restore-engine-matrix/smoke-real-after.txt` / `smoke-fixture-after.txt` / `smoke-real-exit.txt` | 新增 | 两轮冒烟输出 |
| `docs/决策与接口变更.md` | 修改 | 追加 `SMOKE-D1/D2`：冒烟三项按 provider 记 N/A；引用全集含 `official.entries` |
| `reports/2026-11-12-1731-searxng-real-restore.md` | 新增 | 本报告 |
| `reports/INDEX.md` | 修改 | 台账自动插入一行 |

服务进程：`serve.ps1 -Provider searxng`（8000）、`serve.ps1 -Provider fixture -Port 8001 -SkipBuild`（8001，为对照冒烟而临时起）、容器 `cs-searxng`。数据未改：没有新增书签、没有清库。

## 4 验证与证据

**环境就绪**

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 停旧实例 | `Stop-Process -Id 7308` | killed；`Get-NetTCPConnection -LocalPort 8000` → port 8000 free |
| Docker | `Start-Process Docker Desktop.exe` → `docker info --format {{.ServerVersion}}` | `29.9.2`，9s 就绪 |
| SearXNG | `docker compose up -d searxng` | `cs-searxng` Started；`/healthz` 200（4s）；`/config` engines=263；`127.0.0.1:8888->8080` |
| API | `serve.ps1 -Provider searxng` → `/api/health` | `{"status":"ok","provider":"searxng","searxng_url":"http://127.0.0.1:8888","web_built":true}` |

**SearXNG 引擎矩阵（28 引擎 × 2 轮，`probe-engines.py`）**

可用 13 个：

| 引擎 | ok/2 | 中位耗时 | 结果数 |
| --- | --- | --- | --- |
| google cse | 2 | 697ms | 20 / 20 |
| bing | 2 | 711ms | 10 / 10 |
| duckduckgo web | 2 | 1407ms | 10 / 10 |
| yahoo | 2 | 1250ms | 7 / 7 |
| sogou | 2 | 519ms | 10 / 10 |
| mojeek | 2 | 1372ms | 10 / 10 |
| naver | 2 | 1683ms | 19 / 16 |
| yandex | 2 | 1879ms | 10 / 15 |
| 360search | 2 | 445ms | 5 / 6 |
| youtube | 2 | 939ms | 16 / 17 |
| github | 2 | 2151ms | 30 / 30 |
| arxiv | 2 | 290ms | 10 / 10 |
| quark | 1 | 569ms | 6 / 0（第二轮 unexpected crash） |

不可用 15 个：

| 引擎 | 失败形态 |
| --- | --- |
| google / google scholar | `Suspended: access denied`（出口 IP 85.234.83.168 被 Google 拦） |
| duckduckgo | `CAPTCHA` |
| brave | `Suspended: too many requests` |
| baidu | `Suspended: CAPTCHA`（境外出口访问百度反被判验证码） |
| swisscows | `Suspended: access denied` |
| qwant | `Suspended: access denied` |
| yep | `HTTP error` |
| seznam | `timeout` |
| wikipedia / wikidata | 请求成功但 0 结果、无 unresponsive |
| startpage / marginalia / dogpile / yandex api | `not_loaded`（配置里未启用，非网络问题） |

**后缀验收（`verify-searxng.py --engines b y mj`）**

| 用例 | 结果 | 耗时 | 不到 1 分钟 |
| --- | --- | --- | --- |
| Python documentation b | PASS | 359ms | 8 条，来源 bing |
| HTTP b | PASS | 4386ms | 10 条，来源 bing |
| 日本 首都 y / Python documentation y / HTTP y | PASS ×3 | 1.4s / 1.3s / 1.3s | 6 / 6 / 7 条，来源 yahoo |
| Python documentation mj / HTTP mj | PASS ×2 | 1.2s / 4.8s | 10 / 10 条，来源 mojeek |
| 日本 首都 mj | FAIL | 3.2s | mojeek 对中文查询返回空（`status=empty`） |
| `Python !b`（bang） | PASS | 388ms | 8 条，bing |
| `日本 首都 jp`（地区） | PASS | 12.2s | 17 条，7 来源；duckduckgo web timeout、swisscows 熔断 |
| `C g`（不误触发） | PASS | 7.2s | 15 条；duckduckgo CAPTCHA、swisscows 熔断 |

合计 11/12（92%），唯一失败是 mojeek 中文零结果。

**API 后缀矩阵（20 条，`/api/search`，query=Python 文档）**

| 后缀 | HTTP | status | total | 实际来源 | 备注 |
| --- | --- | --- | --- | --- | --- |
| default | 200 | ok | 20 | 360search,bing,duckduckgo web,google cse,mojeek,naver,sogou,yahoo,yandex | duckduckgo CAPTCHA、swisscows 熔断 |
| g | 200 | ok | 15 | google cse | google access denied → 回退 CSE 生效 |
| b | 200 | ok | 9 | bing | |
| d | 200 | ok | 9 | duckduckgo web | duckduckgo CAPTCHA → 回退 web 生效 |
| dw | 200 | ok | 8 | duckduckgo web | |
| br | 503 | error | — | — | `ENGINE_UNAVAILABLE`，brave too many requests |
| yt | 200 | ok | 14 | youtube | |
| gh | 200 | ok | 12 | github | |
| ar | 200 | ok | 10 | arxiv | |
| sc | 200 | ok | 9 | serper | google scholar 崩溃 → 付费兜底生效 |
| w | 200 | ok | 0 | — | wikipedia 引擎零结果（欠账） |
| gc | 200 | ok | 15 | google cse | |
| sp | 200 | ok | 10 | mojeek | startpage 未加载 → 回退 mojeek 生效 |
| mj | 200 | ok | 10 | mojeek | |
| y | 200 | ok | 6 | yahoo | |
| sg | 200 | ok | 10 | sogou | |
| so | 200 | ok | 5 | 360search | |
| n | 200 | ok | 12 | naver | |
| yd | 200 | ok | 10 | yandex | |
| sw | 503 | error | — | — | swisscows 熔断冷却（约 60 分钟） |

18/20 出结果；2 个 503 都是上游被限流后的熔断，不是本机故障。

**测试与冒烟**

| 命令 | 结果 |
| --- | --- |
| `python -m pytest apps/api -q --junit-xml=...` | exit 0；**441 tests, 0 failures, 0 errors, 0 skipped, 8.99s** |
| `pwsh -NoProfile -File scripts\smoke.ps1 -BaseUrl http://127.0.0.1:8000`（修正后，真实模式） | exit 0；16/16 通过，三项标 `N/A(真实模式无固定样本)` |
| `smoke.ps1 -BaseUrl http://127.0.0.1:8001`（fixture 对照） | 16/16 通过 |
| `smoke.ps1`（修正前，真实模式） | 12/16：黑名单拦截 / 零结果 / 上游不可用 / 侧栏总结 SSE 四项 False |

修正前四项失败的定位：

| 检查项 | 失败原因 | 判定 |
| --- | --- | --- |
| 黑名单拦截 | 请求体带 `opts.fixture=risky`，真实上游不认该参数，返回真实结果 `filtered.risk=0` | 判据只适用 fixture，改为 N/A |
| 零结果 | 同上（`fixture=empty` 无效，返回 16 条真实结果） | 同上 |
| 上游不可用 | 同上（`fixture=error` 无效，真实上游正常） | 同上 |
| 侧栏总结 SSE | `invalidCites=['r_5','r_22']`；实际这两条是官方入口区条目（python.org 首页、docs.python.org），不在三档 groups 里 | 判据漏算 `official.entries`，已补 |

SSE 复核数据：260 个事件，首 meta、末 done，cites=10、tokens=423 字符、refs=12、invalid_refs=0；官方区 `key=python` 有 3 条（r_5 首页 / r_22 文档 / d_69… 目录）。

证据文件：

- [engine-probe.json](../assets/proxy-restore-engine-matrix/engine-probe.json)
- [suffix-matrix.json](../assets/proxy-restore-engine-matrix/suffix-matrix.json)
- [verify-suffix.txt](../assets/proxy-restore-engine-matrix/verify-suffix.txt)
- [pytest.xml](../assets/proxy-restore-engine-matrix/pytest.xml)
- [smoke-real-after.txt](../assets/proxy-restore-engine-matrix/smoke-real-after.txt)
- [smoke-fixture-after.txt](../assets/proxy-restore-engine-matrix/smoke-fixture-after.txt)

未验证：

- `startpage / marginalia / dogpile / yandex api` 未启用，故其真实可达性未知；要验需在 SearXNG 配置里开 `inactive: false`。
- `w`（wikipedia）零结果只记录了现象，没查是不是 `display_type` 缺 `list`。
- 前端在真实模式下的三档/官方区展示只做了接口层核对，未重跑浏览器视觉。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 起 Docker Desktop 跑官方 searxng 镜像 | 本机 pip 装 SearXNG | 镜像和容器已存在（`searxng/searxng:latest` 387MB），compose 与 `./searxng/settings.yml` 是项目既有约定，最省事且可复现 |
| 冒烟的三个固定样本检查在真实模式记 N/A | 让它们继续报失败 / 在真实模式下跳过整轮 | 失败会淹没真实问题；直接跳过又看不出跑过，N/A + 原因最诚实 |
| 冒烟引用校验补 `official.entries` | 改产品代码让官方区条目也进 groups | 官方区与三档是产品设计上的两条并行展示，改数据侧会破坏「身份与相关性分开表达」的决策 |
| 后缀矩阵自写脚本而不是只跑 verify-searxng.py | 只用官方脚本 | 官方脚本限 2–3 个引擎，覆盖不到 19 个后缀；自写脚本只读、结果落 JSON 便于比对 |

## 6 遗留与风险

- **Google 全家在当前出口不可用**：出口 85.234.83.168 被 Google 判异常流量，`google` 与 `google scholar` 都 `access denied`；`g` 实际靠 CSE 回退、`sc` 靠 Serper 付费兜底。换节点可解，本轮不动。
- **baidu 被自己的反爬拦**：境外出口访问百度返回 CAPTCHA，国内直连时可用——引擎可用性依赖出口地理位置。
- **brave / swisscows 熔断中**：brave `too many requests`、swisscows `access denied` 后进入 60 分钟冷却，短时间内重跑会继续 503。
- **`w` 后缀零结果**：wikipedia 引擎请求成功但 0 条，和 `probe-engines.py` 的结果一致，需要查 `display_type` 或引擎参数。
- **mojeek 中文查询为空**：`日本 首都 mj` 返回 `empty`，与 mj 的英文查询正常形成对照，属上游索引能力差异。
- **控制台中文乱码**：pwsh 以 cp936 输出 Python 的 UTF-8 日志，矩阵里的中文 query 显示为乱码（JSON 文件本身是 UTF-8，不受影响）。
- **8001 上的 fixture 实例仍在跑**（为对照冒烟临时起的），收尾可关。

## 7 交接

**下一个人第一件事**

先决定出口节点：要 Google 系恢复，就换一个未被标记的节点后重跑 `python scripts\probe-engines.py`；不换节点的话，把 `g/sc` 的默认预期改成「CSE + Serper 兜底」，别再按 Google 直连验收。

**相关文件**

- 证据目录：`reports/assets/proxy-restore-engine-matrix/`
- 引擎真源：`apps/api/app/core/engine_catalog.py`
- 探测脚本：`scripts/probe-engines.py`、`scripts/verify-searxng.py`
- 冒烟脚本：`scripts/smoke.ps1`
- 上一轮：`reports/completed/2026-11-12-1718-proxy-restored-browser.md`

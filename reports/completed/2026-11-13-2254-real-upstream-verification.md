# 完工报告 · 真实搜索上游复核与站点兜底

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-2254 |
| 开始 | 2026-11-13 22:54 |
| 结束 | 2026-11-13 22:55 |
| 耗时 | 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | test |
| 状态 | 完成 |

## 1 任务

**目标**

补上方案终验里唯一的大缺口：真实 SearXNG 未运行导致冒烟/筛选/浏览器断言只跑过 fixture。本轮启动 Docker 里的 `cs-searxng`，用真实上游复跑，并修掉实测暴露的站点限定漏洞。

**验收标准**

- `cs-searxng` 在 `127.0.0.1:8888` 可用，`/search?format=json` 有结果。
- 真实模式 `smoke.ps1` 全绿；`verify-filters.cjs` 覆盖站点/时间/语言/去重/缓存隔离并全绿。
- 真实模式 `audit-ui.cjs` 全绿。
- 站点限定在服务端兜底：结果主机只能是目标域或其子域。
- pytest 不回归。

**不做**

- 不改搜索排序、评分、官方入口表。
- 不重启用户日常 8000 进程（仍是旧 fixture 进程，见 §6）。

## 2 做了什么

1. **启动上游**：本机 Docker Desktop 之前未启动，`Start-Process` 拉起引擎后 `docker compose up -d searxng`，容器 `cs-searxng` 就绪（`/search?format=json` 返回 34 条）。
2. **真实冒烟**：`smoke.ps1` 16/16，候选 59、展示 20、三档 5/10/5、SSE 10 引用。
3. **真实筛选校验**：新增 `scripts/verify-filters.cjs`，对任意 `--base` 断言站点限定、时间范围、语言、三档去重与缓存隔离。首跑暴露两个真问题：
   - `site:` 交给上游不够——SearXNG 与付费回退会忽略，结果里混进 `www.python.org`、`pythonlang.cn`；
   - 旧缓存被新代码复用，返回未过滤结果。
4. **修复**：路由在去重前按主机名兜底过滤（允许子域）；缓存版本 `search-v7` → `search-v8`，旧条目自然失效。新增 `test_site_filter_drops_other_hosts`（fixture 域内只剩 python.org，不存在的域返回 0）。
5. **真实浏览器断言**：`audit-ui.cjs` 对真实上游跑出 `ALL PASS (253)`。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `apps/api/app/routers/search.py` | 修改 | 站点限定服务端兜底过滤（含子域） |
| `apps/api/app/db/cache.py` | 修改 | 缓存版本 `search-v8` |
| `apps/api/tests/test_search.py` | 修改 | 新增站点过滤用例 |
| `scripts/verify-filters.cjs` | 新增 | 真实上游筛选校验（10 项） |
| `reports/assets/final-acceptance/real/` | 新增 | 真实模式审计 JSON 与截图；`smoke-real.log` |
| `docs/决策与接口变更.md`、`docs/浏览器与UI优化方案.md` | 修改 | 兜底规则与真实验证结论 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `docker compose up -d searxng` + `/search?format=json` | 通过 | 容器运行，34 条结果 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18199`（searxng） | 通过 | 16/16；`有结果 total=20 upstream=59`、三档 5/10/5 |
| `node scripts/verify-filters.cjs http://127.0.0.1:18201` | 通过 | `ALL PASS (10)`：站点只剩 docs.python.org、周筛选 13 条、缓存隔离、严格去重无重复标题 |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18201 --out reports/assets/final-acceptance/real` | 通过 | `ALL PASS (253)` |
| `python -m pytest apps/api -q` | 通过 | 482 项（481 + 站点过滤用例），`[100%]` 无 F/E |

**证据文件**

- `reports/assets/final-acceptance/real/p0-ui-audit.json`、`desktop-light-search.png`、`mobile-dark-search.png`、`mobile-drawer.png`
- `reports/assets/final-acceptance/smoke-real.log`

**未验证**

- Android/iOS 真机安装与系统分享、NVDA/VoiceOver 朗读仍缺设备。
- 站点限定对「目标域 + 大量子域」的上游召回影响未做统计（本轮只看正确性）。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 站点限定在服务端二次过滤 | 只依赖 `site:` | 实测上游与付费回退都会忽略 `site:`，必须兜底 |
| 允许子域匹配（`host.endswith('.' + site)`） | 精确主机匹配 | 用户写 `python.org` 时 `docs.python.org` 应保留 |
| 缓存版本升到 v8 | 手动清缓存表 | 版本号一升旧条目自然失效，部署时无需额外操作 |
| 保留用户日常 8000 进程 | 直接重启成 searxng 模式 | 该进程是用户环境，重启属破坏性操作；只报告现状 |

## 6 遗留与风险

- 日常 `8000` 仍是此前启动的 fixture 旧进程（health 无 `db_path`），未加载本轮 API；要体验真实上游需用 `serve.ps1 -Provider searxng` 重启。
- Docker 引擎是我本轮手动拉起的，`cs-searxng` 为 `restart: unless-stopped`；机器重启后若 Docker Desktop 未自启，SearXNG 不会自动恢复。
- 真实上游结果随网络波动，`verify-filters.cjs` 的条数断言只做「有结果/不超标准去重」这类稳健判断。

## 7 交接

**下一个人第一件事**

用 `serve.ps1 -Provider searxng` 重启日常 8000（或让用户决定），确认 `/opensearch.xml` 与新筛选接口都在；随后按方案 §8.3 补真机与读屏三项。

**相关文件**

- 方案：`docs/浏览器与UI优化方案.md`（§8.2.1 已记录真实模式结果）
- 决策：`docs/决策与接口变更.md`（2026-11-13 · 真实上游复核与站点限定兜底）
- 实现：`apps/api/app/routers/search.py`、`apps/api/app/db/cache.py`
- 验收：`scripts/verify-filters.cjs`、`scripts/smoke.ps1`、`scripts/audit-ui.cjs`
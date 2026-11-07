# 完工报告 · 路线图六项

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261106-2342 |
| 开始 | 2026-11-06 23:42 |
| 结束 | 2026-11-06 23:42 |
| 耗时 | 不到 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

**目标**

按既定顺序执行：真 SearXNG 验收 → 引擎熔断 → git init + CI → 安全 feed 与 `/go` → 语义分或查询扩展 → 书签标签 / 分页 / `/tools` 入口。

**验收标准**

- 每项都有可复现证据；做不到的写成「未达成 + 原因」，不硬凑完成。
- 全量测试、构建、冒烟、浏览器断言不回归。

**不做**

- Android / 真机 PWA；桌面壳（M9 设计）；GSB / URLhaus（无 API key）；向量模型（本机无 embedding 模型）。

## 2 做了什么

1. **真 SearXNG**：Windows 无 Docker，改用「源码 + venv + POSIX shim」原生运行（`pwd`、`os.getuid` 两个 shim），`:8888` 返回真实 JSON；新增 `scripts/measure-search-quality.py` 记录成功率/延迟/引擎可用性。
2. **熔断**：新增 `core/breaker.py`（`engine_health` 表 + 两层熔断），聚合层接入；修掉「所有引擎 CAPTCHA 被误判为实例故障、3 次查询锁站 1 小时」的归因错误（新异常 `EnginesUnresponsive`）。
3. **git + CI**：`git init -b main`，新增 `.github/workflows/ci.yml`（pytest + 内联冒烟 + 前端构建），`git add -A` 暂存 170 个文件（**未提交**，遵循不改历史的约定）。
4. **feed 与 `/go`**：`core/feeds.py`（解析/合并/刷新）+ `POST /api/tools/refresh-feeds`；`core/redirect.py` HMAC 签名 + `routers/go.py` 确认页；可疑结果（0.35≤risk<0.6）带 `go_url`。
5. **查询扩展**：`core/expand.py` 词典（16 条），别名词以 0.35 权重进入覆盖率；`ParsedQuery.expanded` 暴露结果。
6. **标签 / 分页 / 入口**：`bookmark_tags` 全链路（读、筛选、替换、聚合）、搜索页上一页/下一页（空页可返回）、头部「一键添加」。
7. 文档：README 增「真实上游、熔断与中转」；决策追加 M9-D1…D11；`docs/进展与欠账.md` 同步状态。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| [apps/api/app/core/breaker.py](../apps/api/app/core/breaker.py) | 新增 | 引擎健康表与熔断 |
| [apps/api/app/core/feeds.py](../apps/api/app/core/feeds.py) | 新增 | 黑名单 feed 解析/合并/刷新 |
| [apps/api/app/core/redirect.py](../apps/api/app/core/redirect.py) | 新增 | `/go` 签名与校验 |
| [apps/api/app/core/expand.py](../apps/api/app/core/expand.py) | 新增 | 查询扩展词典 |
| [apps/api/app/routers/go.py](../apps/api/app/routers/go.py) | 新增 | 确认中转页 |
| [scripts/measure-search-quality.py](../scripts/measure-search-quality.py) | 新增 | 真实上游质量测量 |
| [.github/workflows/ci.yml](../.github/workflows/ci.yml) | 新增 | CI |
| [apps/api/app/core/aggregator.py](../apps/api/app/core/aggregator.py)、[errors.py](../apps/api/app/core/errors.py)、[searxng.py](../apps/api/app/core/searxng.py) | 修改 | 熔断接入、异常分型 |
| [apps/api/app/core/scoring.py](../apps/api/app/core/scoring.py) | 修改 | 别名权重、覆盖率公式 |
| [apps/api/app/routers/search.py](../apps/api/app/routers/search.py)、[tools.py](../apps/api/app/routers/tools.py) | 修改 | go_url、expanded、feed 刷新 |
| [apps/api/app/db/repo.py](../apps/api/app/db/repo.py)、[routers/bookmarks.py](../apps/api/app/routers/bookmarks.py)、[schemas.py](../apps/api/app/schemas.py) | 修改 | 标签读写与筛选 |
| [apps/api/tests/test_breaker.py](../apps/api/tests/test_breaker.py)、[test_feeds_go.py](../apps/api/tests/test_feeds_go.py)、[test_expand.py](../apps/api/tests/test_expand.py)、[test_tags.py](../apps/api/tests/test_tags.py) | 新增 | 26 例 |
| [apps/web/src/App.tsx](../apps/web/src/App.tsx)、[components/ResultCard.tsx](../apps/web/src/components/ResultCard.tsx)、[BookmarkPage.tsx](../apps/web/src/BookmarkPage.tsx)、[api.ts](../apps/web/src/api.ts)、[types.ts](../apps/web/src/types.ts)、[styles.css](../apps/web/src/styles.css) | 修改 | 分页、标签、go 链接、入口 |
| [README.md](../README.md)、[.env.example](../.env.example)、[docs/决策与接口变更.md](../docs/决策与接口变更.md)、[docs/进展与欠账.md](../docs/进展与欠账.md) | 修改 | 说明与决策 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `python -m pytest apps/api -q -o "addopts="` | 通过 | `261 passed` |
| `npm --prefix apps/web run build` | 通过 | 42 modules |
| `pwsh -File scripts/smoke.ps1` | 通过 | 16/16 |
| `python scripts/measure-search-quality.py --base-url http://127.0.0.1:18092` | 通过 | 8/8 成功，中位 936ms，最大 3303ms，结果 10–15 条 |
| Playwright `check_m9b.js`（7 项） | 通过 | 扩展提示、`/go` 中转、标签、筛选、分页、`/tools`、无 JS 错误 |
| `git status` | — | 已 init，170 个文件已暂存，未提交 |

真实上游实测输出：

```
provider=searxng upstream=http://127.0.0.1:8888
8/8 次成功
延迟 中位 936 ms / 最大 3303 ms
来源：google cse（唯一稳定出结果的引擎）
失败引擎：brave(Suspended: too many requests)、duckduckgo(CAPTCHA)、wikidata(timeout)
```

证据文件：`docs/m9-evidence/real-search.json`、`04-go中转.png`、`05-书签标签.png`。

未验证：GSB / URLhaus（无 key）；Android 真机；`.github/workflows/ci.yml` 在 GitHub 上的首次运行（本地无远端）。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| SearXNG 用源码 + shim 原生跑 | 等有 Docker 再做 | 用户要求按序执行；shim 只补两个 POSIX 符号，改动留在仓库外 |
| 聚合超时 3s → 8s | 保持 3s | 一次聚合请求要覆盖 SearXNG 自己的多引擎 fan-out，实测 3s 稳定失败 |
| 熔断区分实例级与引擎级 | 单一计数器 | 「引擎全 CAPTCHA」不是实例故障，混在一起会误锁整站 |
| GSB / URLhaus 留空 | 编假 feed | 没有 key 就标未接入，比塞假数据诚实 |
| `/go` 用 HMAC 签名 | 明文跳转 | 否则 `/go` 就是开放重定向 |
| 扩展用词典 + 半权 | 直接等权拼接 | 无 embedding；等权会让扩展词盖过用户输入 |
| git 只 init + 暂存不提交 | 直接 commit | 遵循「未经明确要求不 commit」 |

## 6 遗留与风险

- 真实上游只验证了 `google cse`；其他引擎在本机网络下不可用，换网络/部署后需重测。
- 引擎级熔断不影响默认查询集合：默认模式下仍可能「所有引擎都 CAPTCHA → 503」。
- 风险分最高仍到不了 0.6（缺 age/feed 权重），只有黑名单命中会丢结果。
- 查询扩词典只有 16 条，覆盖有限；不是语义模型。
- SearXNG 的 Windows shim 与源码在 `D:\agent\build`，未纳入仓库；换机器要重做（README 有步骤）。
- 未执行初始提交，CI 尚未真正跑过。
- 标签没有「批量管理/重命名」，分页在真实多页结果下只做下一页式翻页。

## 7 交接

**下一个人第一件事**

执行 `git commit -m "init: CleanSearch M0–M9"` 并推到远端，确认 CI 的 pytest 与 build 两个 job 都绿；然后按 `docs/进展与欠账.md` §2 继续补 GSB/URLhaus 与语义分。

**相关文件**

- [进展与欠账](../docs/进展与欠账.md)
- [M9 决策 M9-D1…D11](../docs/决策与接口变更.md)
- [真实上游测量脚本](../scripts/measure-search-quality.py)
- [CI](../.github/workflows/ci.yml)

---

## 8 追加轮次：六项逐条证据

### 8.1 真 SearXNG（2026-11-06 23:33）

- `D:\agent\build\searxng`（depth=1 克隆，排除 `utils/templates` 里带 `:` 的文件名）；
- `D:\agent\build\searxenv` venv 安装 `requirements.txt`；
- `shims/pwd.py` + `shims/sitecustomize.py` 补齐 Windows 缺失的 `pwd` 与 `os.getuid`；
- `GET /search?q=HTTP&format=json` 返回 200、10 条结果；
- 结论：**部分达成**——链路通，但只有一个引擎可用。

### 8.2 熔断

- `engine_health` 表：fails / open_until / last_ok / avg_ms / last_error；
- 显式引擎冷却 → `503 ENGINE_UNAVAILABLE`；实例级 → `503 UPSTREAM_UNAVAILABLE`；
- 回归：`test_all_engines_unresponsive_does_not_open_upstream` 证明引擎全挂不锁站。

### 8.3 git + CI

- `git init -b main`；170 个文件已 `git add`；
- CI 两个 job：api（pytest + 内联冒烟）、web（npm ci + build）；
- 未提交，未接远端。

### 8.4 feed 与 `/go`

- `POST /api/tools/refresh-feeds`：无源 → 400；拉取成功写 `data/blocklist-feeds.txt` 并由 Blocklist 按 mtime 热加载；
- `/go`：合法签名 200 + 域名 + 风险分 + 「仍要访问」；改签名 → 403。

### 8.5 查询扩展

- `数分 知识点` → `parsed.expanded = ["数据分析","数学分析"]`；
- 覆盖率改为 `0.65×原词 + 0.35×别名`，原词命中仍排在别名命中之前；
- ASCII 短码按词边界匹配，`python` 不再被 `py` 误扩展。

### 8.6 标签 / 分页 / 入口

- 标签：添加时填、卡片展示、点击筛选、`PATCH` 替换；
- 分页：第 1 页 ↔ 第 2 页，空页保留「上一页」；
- 头部「一键添加」→ `/tools`。

---

> 注：头部「耗时」由 `close-report.ps1` 按报告起草时间计算；本轮六项实际约 2 小时（含 SearXNG 原生编译安装与三处返工）。

## 9 更正 · 2026-11-07 23:20（P0 收口）

§8.1「只有一个引擎可用」已改善，不改原文，补最新证据：

- SearXNG 设置里启用 `yahoo` / `sogou`（原为 disabled，请求会被忽略并回落默认集）；
- 产品新增后缀 `gc`(google cse) / `y`(yahoo) / `sg`(sogou)，另加 `sp`/`mj` 备用；
- `verify-searxng.py --engines gc y`：**9/9 PASS，exit 0**（`gc` 0.6–0.7s / `y` 1.2–1.3s，含 bang、地区 `jp`、`C g` 护栏）；
- 默认多引擎 8/8 有结果，中位 1,736 ms；冷热缓存 2,783→28 ms；
- 真实搜索接 qwen3.5-4b-local：首字 7.7s、总 18.3s、10 条引用全部绑定。

仍未达成：`b/br/d/sc/sg/w` 在该网络不可用；Compose 未验证（无 Docker）。详见 [进展与欠账](../docs/进展与欠账.md)。

# 完工报告 · P0–P3 复核与全文抓取优化

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261107-1206 |
| 开始 | 2026-11-07 12:06 |
| 结束 | 2026-11-07 12:08 |
| 耗时 | 2 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 完成 |

## 1 任务

执行上一轮的全文抓取优化。用真实搜索的三个公开主题固定快照，比较不同抓取预算、正文数、时延和引用，并逐项复核 P0–P3 中可以就地完善的边界。

## 2 做了什么

1. P0 补指定引擎来源校验。Startpage 被 SearXNG 回退至其他来源时返回 `503 ENGINE_UNAVAILABLE`。成功响应只保留请求的来源。搜索缓存键切至 `search-v3`，隔离旧的错误来源缓存。
2. P1 补 CI 发布冒烟。构建前端后启动隔离的 fixture API，探测就绪，执行仓库原有完整冒烟并关闭进程。
3. P2 对同一批真实来源比较 2.5、4、5 秒，选 4 秒作为侧栏全文默认预算。使用 `SUMMARY_FETCH_TIMEOUT` 可独立调整，快速总结不发正文请求。
4. P3 限制同源 favicon 到完整的栅格图标，旧缓存也按媒体类型判断。栅格图片保留缓存，并带 MIME 与沙盒响应头。
5. 更新进度、待办和接口决策。宿主机、容器抓取以及真实模型端到端分别记录。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `apps/api/app/core/searxng.py`、`core/errors.py`、`core/aggregator.py`、`db/cache.py` | 修复 | 指定来源约束、引擎故障归因与缓存版本 |
| `.github/workflows/ci.yml` | 完善 | API 测试、生产构建和完整离线冒烟在同一作业执行 |
| `apps/api/app/config.py`、`apps/api/app/routers/summarize.py`、`.env.example` | 优化 | 全文侧栏的独立抓取预算，默认 4 秒 |
| `apps/api/app/core/favicon.py`、`apps/api/app/routers/assets.py` | 加固 | SVG 和截断新图标降级，缓存与响应防护 |
| `apps/api/tests/test_searxng_client.py`、`test_content.py`、`test_p3_ops.py` | 回归 | 指定来源、独立预算、网络和旧缓存 SVG |
| `README.md`、`docs/进展与欠账.md`、`docs/决策与接口变更.md` | 同步 | 更新当前进度、边界和后续验收条件 |

## 4 验证与证据

| 命令 | 结果 | 输出摘要 |
| --- | --- | --- |
| `.\scripts\serve.ps1 -Provider searxng -Port 18130 -SkipBuild`，以独立 DB 与 `LLM_PROVIDER=stub` 启动，执行 §8 采集探针 | 通过 | Python asyncio、MDN HTTP Cache-Control、SQLite WAL 分别获取 15、7、13 条。旧 Startpage 返回 200，实际混入 Google CSE、Brave、Yahoo。 |
| §8 宿主机探针，依次在同一批前五个来源上比较 2.5/4/5 秒 | 通过 | 2.5 秒 8/15，4 秒和 5 秒均 10/15。2.5 秒超时 4 次，4 秒超时 1 次，仍有 3 次 HTTP 403。每组每个预算按轮换顺序执行。 |
| 分别设置 `SUMMARY_FETCH_TIMEOUT=2.5` 与 `4.0`，用 `.\scripts\serve.ps1 -Provider searxng -Port 18131 -SkipBuild -DeepSeek` 和 `.\scripts\serve.ps1 -Provider searxng -Port 18132 -SkipBuild -DeepSeek` 复用同一临时 SQLite；运行 §8 端到端探针 | 通过 | 2.5 秒正文 5/15，4 秒 9/15，6 次 SSE 均 `done`，引用 ID、URL 和编号通过。见配对明细。 |
| 对 18132 上的同一快照 `GET /api/summarize?sid=<快照>&mode=fast` | 通过 | 正文抓取 0、失败 0，首段 1,205 ms、总耗时 2,911 ms，10 条引用绑定，8 个有效正文引用编号。 |
| 对 18132 执行 `POST /api/search`，固定查询 `HTTP documentation sp` 与 `MDN HTTP Cache-Control documentation y` | 通过 | Startpage 返回 503 `ENGINE_UNAVAILABLE`，Yahoo 返回 200、7 条 Yahoo 结果。 |
| `python -m pytest apps/api -q -o 'addopts=' -k 'explicit_engine_rejects_default_fallback or explicit_engine_only_keeps_matching_sources or favicon_does_not_serve_svg' --tb=short` | 修复前复现 | 4 项失败。显式引擎接受错误来源，新抓取及旧缓存 SVG 均返回 200。 |
| `python -m pytest apps/api -q -o 'addopts='` | 通过 | `284 passed in 7.70s`。新增 5 项回归均通过。 |
| `npm --prefix apps/web run build` | 通过 | Vite 转换 42 个模块，生产产物生成。 |
| 用 PyYAML `BaseLoader` 从 `.github/workflows/ci.yml` 读取 `verify` 作业的 PowerShell 步骤并执行其 `run`，其中调用 `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18129` | 通过 | Windows 宿主机执行原步骤，`冒烟通过`，16/16，临时目录隔离。GitHub 托管执行待验。 |
| `docker compose config --quiet` | 通过 | `compose_config_exit=0`。 |
| `docker run --rm --pull never -i --network llq_cs --mount "type=bind,source=$public,target=/bench/public-sources.json,readonly" --mount "type=bind,source=$api,target=/app/app,readonly" llq-api python -X utf8 -` | 通过 | 探针使用相同快照的公开 URL 与标题，复用宿主机抓取及提取函数。2.5 秒 8/15，4 秒 11/15，容器超时从 4 次降至 2 次。 |

| 快照主题 | 2.5 秒正文数 / 首段 / 总耗时 | 4 秒正文数 / 首段 / 总耗时 |
| --- | --- | --- |
| Python asyncio TaskGroup | 3/5 · 4,697 ms · 6,177 ms | 3/5 · 5,080 ms · 7,009 ms |
| MDN HTTP Cache-Control | 1/5 · 3,610 ms · 6,036 ms | 3/5 · 5,258 ms · 6,679 ms |
| SQLite WAL | 1/5 · 3,558 ms · 5,071 ms | 3/5 · 4,701 ms · 6,069 ms |

端到端首段中位耗时从 3.61 秒增至 5.08 秒。真实站点与模型均会波动，以上为同批三组配对样本。独立容器只运行受控正文抓取与提取，未发送模型请求。临时实例已停止，现有容器和书签卷继续使用原配置。

## 5 关键决策

- 4 秒预算在同源样本中与 5 秒得到相同正文数量。维持并发前五来源、地址验证、重定向和内容大小限制。
- 指定来源必须在上游结果中可验证。其他来源只在默认搜索正常展示。
- CI 复用仓库完整冒烟，Ubuntu 24.04 镜像提供 PowerShell。[镜像软件清单](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md#powershell-tools)

## 6 遗留与风险

- 4 秒仍会遇到超时、403 或内容不足，已验证保留摘要。全文模式的延迟和收益需用更多主题观察。
- 容器内 DeepSeek 的端到端路径未运行。远端 CI、Chrome 手动加载、原生书签往返与 Android 系统分享留待目标环境。
- GSB、URLhaus 和商业检索兜底等待各自凭据，RDAP 等待批量与缓存方案。

## 7 交接

常规使用默认 4 秒。若更看重全文首段时延，可将 `SUMMARY_FETCH_TIMEOUT` 改为 `2.5`，再以同一批查询对照。仓库配置远端后执行托管 CI，把 16 项发布冒烟结果补入进度。

## 8 复验探针

采集和对照在同一隔离 SQLite 上进行。测试端口 18130–18132，关闭搜索缓存。

### 采集公开快照和验证旧路由

```powershell
@'
import httpx

samples = (
    ("Python asyncio TaskGroup documentation", "gc"),
    ("MDN HTTP Cache-Control documentation", "y"),
    ("SQLite write ahead logging documentation", "gc"),
)
with httpx.Client(base_url="http://127.0.0.1:18130", timeout=15, trust_env=False) as api:
    for title, selected in samples:
        for short in dict.fromkeys((selected, "y", "gc", "")):
            query = f"{title} {short}".strip()
            response = api.post("/api/search", json={"q": query})
            data = response.json()
            hits = [item for group in data.get("groups", {}).values() for item in group]
            engines = sorted({e for hit in hits for e in hit["engine"]})
            if len(hits) >= 5:
                print(f"sample={title!r} route={short or 'default'} hits={len(hits)} engines={engines}", flush=True)
                break
            print(f"retry={title!r} route={short or 'default'} status={response.status_code} hits={len(hits)}", flush=True)
        else:
            raise SystemExit(1)
    before = api.post("/api/search", json={"q": "HTTP documentation sp"})
    data = before.json()
    print(f"route_guard_before_http={before.status_code} routed={data.get('parsed',{}).get('engine')} engines={data.get('meta',{}).get('engines')} error={data.get('error',{}).get('code')}")
'@ | python -X utf8 -
```

### 宿主机三种抓取预算对照

```powershell
@'
import asyncio
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time

sys.path.insert(0, str(Path("apps/api").resolve()))
from app.core.extract import extract_article
from app.core.fetch import FetchError, SafeFetcher

db = max(Path(tempfile.gettempdir()).glob("llq-p0p3-benchmark-*/review.db"), key=lambda file: file.stat().st_mtime)
with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
    rows = conn.execute("SELECT query, sources FROM search_sessions ORDER BY rowid LIMIT 3").fetchall()
assert len(rows) == 3
assert all(len(json.loads(raw)) >= 5 for _, raw in rows)

async def inspect(fetcher, source):
    try:
        page = await fetcher.fetch(source["url"])
    except FetchError as exc:
        return f"HTTP_{exc.status}" if exc.status is not None else exc.code
    article = await asyncio.to_thread(extract_article, page.text, page.url, source["title"])
    return "ok" if len(article.text.strip()) >= 80 else "short"

async def run():
    budgets = (2.5, 4.0, 5.0)
    totals = {budget: Counter() for budget in budgets}
    for index, (query, raw) in enumerate(rows):
        sources = json.loads(raw)[:5]
        for budget in budgets[index:] + budgets[:index]:
            fetcher = SafeFetcher(timeout=budget, extra_cidrs=("198.18.0.0/15",))
            start = time.perf_counter()
            counts = Counter(await asyncio.gather(*(inspect(fetcher, source) for source in sources)))
            totals[budget].update(counts)
            elapsed = round((time.perf_counter() - start) * 1000)
            print(f"sample={index+1} budget={budget} elapsed_ms={elapsed} counts={dict(counts)}", flush=True)
    print(f"totals={dict(totals)}")

asyncio.run(run())
'@ | python -X utf8 -
```

### 同一批快照端到端对照

```powershell
@'
from collections import Counter
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import time

import httpx

db = max(Path(tempfile.gettempdir()).glob("llq-p0p3-benchmark-*/review.db"), key=lambda file: file.stat().st_mtime)
with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
    rows = conn.execute("SELECT sid, sources FROM search_sessions ORDER BY rowid LIMIT 3").fetchall()
assert len(rows) == 3
ports = (18131, 18132)
totals = Counter()
with httpx.Client(timeout=50, trust_env=False) as api:
    for port in ports:
        health = api.get(f"http://127.0.0.1:{port}/api/health").raise_for_status().json()
        assert (health["provider"], health["llm_model"]) == ("searxng", "deepseek-flash")
    for index, (sid, raw) in enumerate(rows):
        sources = json.loads(raw)[:10]
        for port in (ports if index % 2 == 0 else ports[::-1]):
            base = f"http://127.0.0.1:{port}"
            name = ""
            events = []
            first_ms = None
            start = time.perf_counter()
            with api.stream("GET", base + "/api/summarize", params={"sid": sid, "mode": "full"}) as res:
                res.raise_for_status()
                for line in res.iter_lines():
                    if line.startswith("event: "):
                        name = line[7:]
                    elif line.startswith("data: "):
                        payload = json.loads(line[6:])
                        events.append((name, payload))
                        if first_ms is None and name == "token" and payload["t"].strip():
                            first_ms = round((time.perf_counter() - start) * 1000)
            total_ms = round((time.perf_counter() - start) * 1000)
            meta = dict(events)["meta"]
            cites = [payload for name, payload in events if name == "cite"]
            expected = [(index, item["result_id"], item["url"]) for index, item in enumerate(sources, 1)]
            actual = [(item["i"], item["result_id"], item["url"]) for item in cites]
            text = "".join(payload["t"] for name, payload in events if name == "token")
            refs = {int(match) for match in re.findall(r"\[(\d+)\]", text)}
            partial = bool(meta["failed"] or meta["truncated"])
            assert first_ms is not None and refs and refs <= {cite["i"] for cite in cites}
            assert events[-1][0] == "done" and actual == expected
            assert meta["fetched"] == sum(cite["material"] != "snippet" for cite in cites)
            assert meta["failed"] + meta["fetched"] == 5
            assert meta["degraded"] == dict(events)["done"]["partial"] == partial
            totals[port] += meta["fetched"]
            print(f"sample={index+1} port={port} fetched={meta['fetched']} failed={meta['failed']} first_ms={first_ms} total_ms={total_ms} cites={len(cites)} refs={len(refs)} done=ok", flush=True)
print(f"paired_endpoint_totals={dict(totals)}")
'@ | python -X utf8 -
```

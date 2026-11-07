# 完工报告 · 真实搜索接 DeepSeek 双模式验收与时延指标修复

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261107-1148 |
| 开始 | 2026-11-07 11:48 |
| 结束 | 2026-11-07 11:49 |
| 耗时 | 2 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 完成 |

## 1 任务

完成上一轮交接的真实 SearXNG 接 DeepSeek 联调。对三个公开技术主题逐一执行 fast/full，核对指定搜索来源、首段正文、结束事件、引用绑定和全文抓取降级。复验发现的 SSE 耗时统计偏差纳入修复。

## 2 做了什么

1. 用独立回环端口和临时 SQLite 库启动 `-Provider searxng -DeepSeek`，以 Google CSE 和 Yahoo 返回的真实搜索结果作为材料。三个主题各两种模式，6/6 正常结束。
2. 发现 `/api/metrics` 在响应头发出时就记账，几秒钟的流式总结被记成毫秒级。改在响应正文完成时记录，并新增并发回归用例，验证仍在生成的总结不会计入。
3. 用 Yahoo 的真实查询复验修复后的 fast/full，两次都正确完成。应用 p95 与客户端最大完整耗时相差约 1.2 ms。
4. 对本轮快照里的前五条材料单独重试受控抓取，统计超时与 403。同步进度与决策文档。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `apps/api/app/core/metrics.py`、`apps/api/app/main.py` | 修复 | ASGI 在正文最后一帧或文件委托发送后记账。未完成即异常的请求记录为 500 |
| `apps/api/tests/test_p3_ops.py` | 回归 | 总结暂停在首段之前时，查询指标未计入。发送结束后只增加一条成功记录 |
| `README.md`、`docs/进展与欠账.md`、`docs/决策与接口变更.md` | 更新 | 真实联调结果、全文降级及 HTTP 指标口径 |
| 本报告与 `reports/INDEX.md` | 登记 | 完整证据和验收边界 |

## 4 验证与证据

| 命令 | 结果 | 输出摘要 |
| --- | --- | --- |
| `.\scripts\serve.ps1 -Provider searxng -Port 18124 -SkipBuild -DeepSeek`，运行 §8 第一条探针（默认端口） | 通过 | 真实搜索 3/3，fast/full 6/6，0 个失配引用，6 次均 `done`。每组输出见下表 |
| `Invoke-RestMethod http://127.0.0.1:18124/api/metrics` | 复现 | 原版 `summary_request_count=6 summary_p50_ms=1.4 summary_p95_ms=2.5`，与实际 2.18–5.15 秒不符 |
| `python -m pytest apps/api -q -o 'addopts=' -k summary_metrics_wait_until_response_finishes --tb=short` | 修复前失败 | 总结仍在等待正文时，指标已经计入 1 条。修复后由完整回归覆盖 |
| `.\scripts\serve.ps1 -Provider searxng -Port 18125 -SkipBuild -DeepSeek`，§8 第一条探针追加 `--base-url http://127.0.0.1:18125 --sample 1` | 上游失败 | Google CSE 复测 HTTP 503，`UPSTREAM_UNAVAILABLE`，3,227 ms，未触发模型调用 |
| 同一服务，§8 第一条探针改为 `--base-url http://127.0.0.1:18125 --sample 2`，然后 `Invoke-RestMethod http://127.0.0.1:18125/api/metrics` | 通过 | Yahoo 7 条结果，fast/full 2/2。客户端 2,269/5,182 ms，应用 `count=2 errors=0 p50=2268 p95=5180.8` |
| §8 第二条探针重试同一批公开 URL | 通过 | 15 次正文探测，5 次可用、8 次超时、2 次 HTTP 403。单次结果可能随上游变化 |
| `python -m pytest apps/api -q -o 'addopts='` | 通过 | `279 passed in 7.40s` |
| `npm --prefix apps/web run build` | 通过 | TypeScript 通过，Vite 转换 42 个模块并生成发布产物 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18126` | 通过 | `冒烟通过`，固定样本 16/16 |

| 固定公开主题 | 指定来源及结果数 | fast 首段/总耗时（ms） | full 首段/总耗时（ms） | full 正文 |
| --- | --- | --- | --- | --- |
| Python asyncio TaskGroup | Google CSE，15 条 | 775 / 2,175 | 3,442 / 5,146 | 2/5，降级 3 |
| MDN HTTP Cache-Control | Yahoo，7 条 | 1,506 / 2,411 | 3,495 / 4,747 | 3/5，降级 2 |
| SQLite WAL | Google CSE，12 条 | 973 / 2,392 | 3,339 / 4,608 | 0/5，降级 5 |

耗时从发起 SSE 请求起算，包含 full 抓取时间，独立于搜索耗时。每次响应核对了编号连续、引用 URL 和 ID 对应快照，以及正文编号均存在于引用列表。真实性和引用关联只覆盖本次样本。临时服务 18124–18126 已关闭。

## 5 关键决策

- 以端到端接收首段与结束事件评估总结，HTTP 请求指标计量整段响应。应用层 SSE `error` 事件保持原协议。
- 保持受控抓取预算。全文失败保留摘要，`degraded`、`partial` 与材料计数必须一致。

## 6 遗留与风险

- 初测全文抓取仅 5/15。复探的主要失败类型是超时，其次是 HTTP 403。仍需更稳定的可抓取来源。
- Google CSE 复测出现一次 503。Yahoo 复测正常，搜索引擎成功率仍会波动。
- 指标分组统计 HTTP 响应状态。模型错误若由 SSE `error` 表达，仍需单独核对该事件。

## 7 交接

常规使用 `.\scripts\serve.ps1 -Provider searxng -DeepSeek`。优先量化全文模式的成功率与首段时延，再评估是否调整可抓取来源选择。保持固定样本冒烟与真实联调分开。

## 8 复验探针

双模式探针只输出结构校验、计数和耗时。启动验收服务时使用新的临时数据库，并保持 `CACHE_ENABLED=false`。

```powershell
@'
import argparse
import json
import re
import time

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:18124")
parser.add_argument("--mode", choices=("fast", "full"), action="append")
parser.add_argument("--sample", type=int, choices=(1, 2, 3), action="append")
args = parser.parse_args()
samples = (
    "Python asyncio TaskGroup documentation gc",
    "MDN HTTP Cache-Control documentation y",
    "SQLite write ahead logging documentation gc",
)
modes = args.mode or ("fast", "full")
indices = args.sample or (1, 2, 3)
failed = False
with httpx.Client(base_url=args.base_url, timeout=50, trust_env=False) as client:
    health = client.get("/api/health").raise_for_status().json()
    assert (health["provider"], health["llm_provider"], health["llm_model"]) == ("searxng", "openai", "deepseek-flash")
    print("provider=searxng llm=deepseek-flash", flush=True)
    for index in indices:
        q = samples[index - 1]
        start = time.perf_counter()
        response = client.post("/api/search", json={"q": q})
        search_ms = round((time.perf_counter() - start) * 1000)
        data = response.json()
        if not response.is_success:
            print(f"sample={index} search_http={response.status_code} code={data.get('error', {}).get('code')} ms={search_ms}", flush=True)
            failed = True
            continue
        hits = {item["id"]: item for group in data["groups"].values() for item in group}
        sources = sorted({engine for hit in hits.values() for engine in hit["engine"]})
        engine = data["parsed"]["engine"]
        expected_engine = "yahoo" if q.endswith(" y") else "google cse"
        print(f"sample={index} search_ms={search_ms} engine={engine} actual={','.join(sources)} results={len(hits)}", flush=True)
        if not hits or engine != expected_engine or expected_engine not in sources:
            failed = True
            continue
        for mode in modes:
            meta, done = {}, {}
            citations = []
            tokens = []
            first_ms = None
            name, last, error = "", "", None
            start = time.perf_counter()
            with client.stream("GET", "/api/summarize", params={"sid": data["meta"]["sid"], "mode": mode}) as stream:
                stream.raise_for_status()
                for line in stream.iter_lines():
                    if line.startswith("event: "):
                        name = line[7:]
                    elif line.startswith("data: "):
                        event = json.loads(line[6:])
                        last = name
                        if name == "meta":
                            meta = event
                        elif name == "cite":
                            citations.append(event)
                        elif name == "token":
                            tokens.append(event["t"])
                            if first_ms is None and event["t"].strip():
                                first_ms = round((time.perf_counter() - start) * 1000)
                        elif name == "done":
                            done = event
                        elif name == "error":
                            error = event["code"]
            elapsed = round((time.perf_counter() - start) * 1000)
            text = "".join(tokens)
            refs = {int(match) for match in re.findall(r"\[(\d+)\]", text)}
            grouped = re.findall(r"\[\d+(?:[,，、–-]\s*\d+)+\]", text)
            numbers = [cite["i"] for cite in citations]
            broken = sum(cite["url"] != hits.get(cite["result_id"], {}).get("url") for cite in citations)
            invalid = len(refs - set(numbers))
            materials = {kind: sum(cite["material"] == kind for cite in citations) for kind in ("snippet", "full", "truncated")}
            expected_attempted = min(len(citations), 5) if mode == "full" else 0
            fetched = meta.get("fetched", 0)
            fetch_failed = meta.get("failed", 0)
            truncated = meta.get("truncated", 0)
            partial = bool(fetch_failed or truncated)
            valid = all((
                not error, last == "done", first_ms is not None, refs, not broken, not invalid,
                numbers == list(range(1, len(citations) + 1)), meta.get("sources") == len(citations),
                meta.get("model") == "deepseek-flash", meta.get("mode") == mode,
                done.get("mode") == mode, done.get("tokens") == len(tokens),
                fetched + fetch_failed == expected_attempted,
                fetched == materials["full"] + materials["truncated"],
                truncated == materials["truncated"],
                meta.get("degraded") is partial, done.get("partial") is partial,
            ))
            print(
                f"sample={index} mode={mode} valid={valid} first_ms={first_ms} elapsed_ms={elapsed} "
                f"cites={len(citations)} refs={len(refs)} bad_bindings={broken} invalid_refs={invalid} "
                f"grouped={len(grouped)} fetched={fetched} failed={fetch_failed} truncated={truncated} "
                f"partial={partial} last={last} error={error}", flush=True,
            )
            failed |= not valid
raise SystemExit(int(failed))
'@ | python -X utf8 -
```

正文诊断只读初测临时库。它单独复探每组前五个公开结果，环境使用本机已配置的透明代理网段。

```powershell
@'
import asyncio
import collections
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path("apps/api").resolve()))
from app.core.extract import extract_article
from app.core.fetch import FetchError, SafeFetcher

db = max(Path(tempfile.gettempdir()).glob("llq-deepseek-live-*/review.db"), key=lambda file: file.stat().st_mtime)
with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
    rows = conn.execute("SELECT sources FROM search_sessions WHERE provider='searxng' ORDER BY created_at").fetchall()
assert len(rows) == 3
fetcher = SafeFetcher(timeout=2.5, extra_cidrs=("198.18.0.0/15",))

async def inspect(source):
    try:
        page = await fetcher.fetch(source["url"])
    except FetchError as exc:
        return f"HTTP_{exc.status}" if exc.status is not None else exc.code
    article = await asyncio.to_thread(extract_article, page.text, page.url, source["title"])
    return "正文可用" if len(article.text.strip()) >= 80 else "正文过短"

async def run():
    overall = collections.Counter()
    for index, (source_json,) in enumerate(rows, 1):
        sources = json.loads(source_json)[:5]
        counter = collections.Counter(await asyncio.gather(*(inspect(source) for source in sources)))
        print(f"reprobe_sample={index} counts={dict(counter)}", flush=True)
        overall.update(counter)
    print(f"reprobe_total={dict(overall)}")

asyncio.run(run())
'@ | python -X utf8 -
```

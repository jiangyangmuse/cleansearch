# 完工报告 · Serper 真实兜底验收与容器云端链路

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261107-1437 |
| 开始 | 2026-11-07 14:37 |
| 结束 | 2026-11-07 14:39 |
| 耗时 | 2 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 完成 |

## 1 任务

补做 DSH 的真实 Serper 接口和 18 条标注查询开关对照，并推进欠账中的容器云端总结验证。使用公开查询和隔离数据库，记录质量指标、延迟、主上游故障恢复及引用绑定。

## 2 做了什么

1. 把用户提供的 Serper 凭据写入 Git 忽略的本地配置。先用真实适配器确认认证和响应，再补主上游错误时未调用兜底的路径。
2. 主上游连接失败、引擎全部失败和实例熔断时均可调用 Serper。付费来源单独记录健康状态，冷却中跳过。固定样本、显式引擎和后续页不调用付费来源。
3. 付费响应复用主 URL 校验，错误结构转为来源错误。去重统一交给主检索管线，保留重复结果的两个来源。缓存区分扩展模式和付费来源。
4. 扩展现有评估脚本，用全部 18 条标注查询交替请求关闭/开启实例。结果保存到 `reports/assets/serper-validation/labelled-comparison.json`。
5. 用隔离容器完成 Serper 真故障兜底接 DeepSeek 的 fast/full。诊断 IPv6 解析导致的抓取拒绝，改用系统已配置的地址族，随后以官方文档限定查询验证实际正文。
6. 更新进度、README 和 M15 决策，并更正旧文档把 act 镜像缺少 PowerShell 泛化到托管 runner 的说法。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `apps/api/app/core/aggregator.py` | 修复 | 故障兜底、付费熔断、来源去重交接和固定样本保护 |
| `apps/api/app/core/paid.py` | 修复 | 安全归一化和异常响应分类 |
| `apps/api/app/core/fetch.py` | 修复 | DNS 使用系统已配置的地址族，继续检查所有返回地址并钉扎连接 |
| `apps/api/app/routers/search.py`、`apps/api/app/db/cache.py` | 修复 | 缓存命名空间及 `search-v4` |
| `apps/api/tests/test_paid.py`、`apps/api/tests/test_cache.py` | 回归 | 故障与熔断、固定样本、异常返回、开关缓存和双来源去重 |
| `scripts/eval-expansion.py` | 完善 | 新增 `--compare-base-url`，沿用原标注集及域名命中指标 |
| `README.md`、`docs/进展与欠账.md`、`docs/决策与接口变更.md` | 同步 | 实测、适用边界和后续事项 |
| 本地 `.env` | 配置 | 已确认 Git 忽略，凭据未写入示例或报告 |

## 4 验证与证据

| 命令 | 结果 | 输出摘要 |
| --- | --- | --- |
| 用 `PaidSearch(settings).search('Python asyncio documentation', region='us')` 调用官方端点 | 通过 | `serper_real_results=9 engine=serper error=none` |
| `python -m pytest apps/api/tests/test_paid.py -q -o 'addopts=' --tb=short` | 修复前复现 | 7 failed、6 passed。主上游错误或熔断直接抛错，固定样本调用了付费接口，异常 JSON 结构未受控。 |
| 在 18140/18141 启动 `.\scripts\serve.ps1 -Provider searxng -SkipBuild`，分别设置 `PAID_FALLBACK=false/true`、独立 DB、`CACHE_ENABLED=false`、`EXPANSION_MODE=rank` | 通过 | 两侧配置相同主上游，测试数据隔离。 |
| `python scripts/eval-expansion.py --base-url http://127.0.0.1:18140 --compare-base-url http://127.0.0.1:18141 --json-out reports/assets/serper-validation/labelled-comparison.json` | 通过 | 两侧各 18/18 成功，无缓存。开启侧 18/18 有 Serper，0 个 Serper 错误，详见下表。 |
| 18142 临时实例设 `SEARXNG_URL=http://127.0.0.1:18149`、`BREAKER_FAILS=1` 并启用 DeepSeek，运行 §8 探针的同类流程 | 通过 | 两次搜索均 10 条、来源为 Serper，主上游失败仍可出结果。fast 首段 1,164 ms，总 1,806 ms；full 首段 794 ms，总 1,900 ms，正文 0/5，摘要降级且引用有效。 |
| 隔离容器初测相同查询并比较 DNS 结果 | 诊断 | fast 首段 938 ms、总 2,163 ms，full 正文 0/5。每条解析都包含未配置的 IPv6，且出现 `2001:2::` 保留地址，安全检查拒绝。带 `AI_ADDRCONFIG` 的同源解析仅返回已配置的 IPv4，五条均通过地址判定。 |
| 只读挂载当前 API 和前端，用临时 `--env-file` 启动独立 `llq-api` 容器于 18143，运行 §8 探针 | 通过 | 固定查询 `asyncio TaskGroup site:docs.python.org`，Serper 兜底 8 条。fast 首段 674 ms、总 1,532 ms；full 正文 5/5、首段 3,162 ms、总 4,296 ms。两个模式均正常 done、8 条引用绑定、5 个有效正文编号。 |
| `python -m pytest apps/api -q -o 'addopts='` | 通过 | `302 passed in 7.85s`，含现有 SSRF 和 DNS 校验回归。 |
| `npm --prefix apps/web run build` | 通过 | TypeScript 通过，Vite 转换 42 个模块并生成产物。 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18144` | 通过 | 真实凭据在本地配置中，fixture 离线流程仍 `冒烟通过`，16/16。 |
| `python scripts/ci-smoke.py http://127.0.0.1:18144` | 通过 | DSH 的跨平台版本 15/15。 |
| 对已跟踪文件、暂存区和本轮 JSON 扫描两种真实凭据 | 通过 | `credentials_absent_from_tracked_files_index_and_evidence=true`。 |

| 全部 18 条样本 | 关闭付费补充 | 开启 Serper |
| --- | --- | --- |
| 请求成功 | 18/18 | 18/18 |
| 期望域名 Top10 命中 | 6/18 | 11/18 |
| 期望域名进入强相关 | 0/18 | 2/18 |
| 延迟中位 | 1,548.5 ms | 4,700 ms |
| 延迟 P95 | 3,084 ms | 5,813 ms |

标注集使用预设域名列表，指标表示这些域名是否在可见结果中。P95 使用最近秩，18 条样本时为最大值。两侧按查询轮换顺序，原始结构数据已保存。宿主机与容器成功样本的查询不同，5/5 不能解读为原先同一组正文从 0/5 恢复。

## 5 关键决策

- 保留 DSH 的第一页付费补充，并补上故障兜底。实测提升与延迟代价同时登记，`PAID_FALLBACK=false` 可暂停。
- 复用主归一化与去重，使付费结果遵守现有 URL 边界，重复条目保留来源信息。
- DNS 按系统配置选择地址族。返回地址仍逐一验证，本文没有加入新的地址例外。

## 6 遗留与风险

- Brave 真实接口仍无对应凭据，本轮实际调用只验证 Serper。
- 18 条标注查询和一条官方文档 full 成功样本不能代表所有查询。真实来源仍可能 403、超时或缺正文。
- GitHub Actions 托管执行、Chrome 手动加载与 Android 真机仍待相应环境。本轮复测了跨平台冒烟，DSH 的 act 记录保留为本地证据。

## 7 交接

可从工作区运行 `.\scripts\serve.ps1 -Provider searxng -DeepSeek` 使用本地配置中的 Serper 与 DeepSeek。继续用更大的标注集观察期望域名命中和延迟，正式接入远端后再验证托管 CI。

临时回环服务与隔离容器已关闭，临时容器凭据文件已删除。本地 `.env` 保留用户授权的 Serper 配置。

## 8 容器成功样本探针

容器主上游故意指向其自身的空闲回环端口，两个外部端点均使用官方服务。此探针可在相同隔离服务准备好后复验。

```powershell
@'
import json
import re
import time

import httpx

with httpx.Client(base_url="http://127.0.0.1:18143", timeout=50, trust_env=False) as api:
    health = api.get("/api/health").raise_for_status().json()
    assert health["llm_model"] == "deepseek-flash" and health["provider"] == "searxng"
    print("container_provider=searxng cloud_model=deepseek-flash", flush=True)
    for turn in range(1):
        response = api.post("/api/search", json={"q": "asyncio TaskGroup site:docs.python.org"})
        body = response.raise_for_status().json()
        results = {item["id"]: item for group in body["groups"].values() for item in group}
        assert results and body["meta"]["engines"] == ["serper"]
        assert all(item["engine"] == ["serper"] for item in results.values())
        assert any(item.startswith("searxng(") for item in body["meta"]["unresponsive"])
        print(f"fault_search={turn+1} results={len(results)} engines={body['meta']['engines']} unresponsive={body['meta']['unresponsive']}", flush=True)
    for mode in ("fast", "full"):
        events = []
        event = ""
        first_ms = None
        start = time.perf_counter()
        with api.stream("GET", "/api/summarize", params={"sid": body["meta"]["sid"], "mode": mode}) as stream:
            stream.raise_for_status()
            for line in stream.iter_lines():
                if line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])
                    events.append((event, data))
                    if first_ms is None and event == "token" and data["t"].strip():
                        first_ms = round((time.perf_counter() - start) * 1000)
        cites = [data for name, data in events if name == "cite"]
        text = "".join(data["t"] for name, data in events if name == "token")
        refs = {int(value) for value in re.findall(r"\[(\d+)\]", text)}
        assert events[-1][0] == "done" and refs and refs <= {cite["i"] for cite in cites}
        assert all(cite["url"] == results[cite["result_id"]]["url"] for cite in cites)
        meta = dict(events)["meta"]
        print(f"fault_summary mode={mode} first_ms={first_ms} total_ms={round((time.perf_counter()-start)*1000)} cites={len(cites)} refs={len(refs)} fetched={meta['fetched']} failed={meta['failed']} done=ok", flush=True)
'@ | python -X utf8 -
```

# 完工报告 · RDAP 复核优化与四十域名校准

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261107-1506 |
| 开始 | 2026-11-07 15:06 |
| 结束 | 2026-11-07 15:07 |
| 耗时 | 2 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 完成 |

## 1 任务

复查 DSH 的 RDAP 域名年龄交付，修复可复现的问题，并完成交接中的 20 个钓鱼来源、20 个正常参考域名校准与批次负载测量。公开 feed 只用于取样，实际网络访问限于 feed 与 RDAP 服务。

## 2 做了什么

1. 将每个域名单独超时改为整个搜索批次含排队共用 4 秒预算。缓存读写移到工作线程，设置短暂锁等待，派生缓存不可用时搜索继续。
2. 使用包内 PSL 把子域归一到注册域名，声明现有 tld 包为核心依赖。新旧子域查询可共享注册域名缓存。
3. 429、超时和服务故障不写入一天的负缓存。修复异常 JSON、无时区和未来注册日期；旧的未来日期缓存会重新查询。派生表限制 4,096 项。
4. 搜索打分保留年龄理由，风险确认页只读年龄缓存并显示相同风险增量。固定样本模式只读缓存，搜索缓存区分 RDAP 启停和策略版本。
5. 新增 `scripts/eval-rdap.py`，从 OpenPhish 取 20 个注册域名，并与 20 个预设参考域名对照。结果记录 feed 哈希、时间和去链接化域名。
6. 完成校准和单批八域名负载测量。数据不足以支持提高权重，保留 30 天与 0.15。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `apps/api/app/core/rdap.py` | 修复 | 注册域名、预算、缓存、解析及降级 |
| `apps/api/app/routers/search.py`、`apps/api/app/routers/go.py` | 修复 | 缓存依赖、离线模式、风险理由和确认页 |
| `apps/api/pyproject.toml` | 依赖 | 显式声明 tld，运行环境已有 0.13.2 |
| `apps/api/tests/test_rdap.py` | 回归 | 新增预算、短暂故障、子域、异常日期、旧缓存、解释和离线保护 |
| `scripts/eval-rdap.py` | 新增 | 20+20 公开域名校准及固定样本重放 |
| `.env.example`、`README.md`、`docs/决策与接口变更.md`、`docs/进展与欠账.md` | 同步 | 配置与当前验收边界 |
| `reports/assets/rdap-review/calibration.json`、`load.json` | 证据 | 校准和负载输出 |

## 4 验证与证据

| 命令 | 结果 | 输出摘要 |
| --- | --- | --- |
| `python -m pytest apps/api/tests/test_rdap.py -q -o 'addopts=' --tb=short` | 修复前复现 | 6 failed、3 passed。排队查询突破批次预算、429 被负缓存、子域不共享记录，异常结构与未来时间未正确处理。 |
| 本机按现有配置设置 `FETCH_EXTRA_CIDRS`，执行 `python scripts/eval-rdap.py --db-path data/rdap-calibration-review.db --json-out reports/assets/rdap-review/calibration.json` | 通过 | 20 个 feed 来源与 20 个参考域名，注册时间分别可得 18/20 和 19/20；所有域名去链接化，原始 feed 哈希和采集时间保存在证据。 |
| §8 负载探针，以 `PYTHONPATH=apps/api` 运行 | 通过 | `warm_eight_ms=21 slow_eight_ms=4015 network_started=4 network_queued_skipped=4`。慢响应为受控 MockTransport。 |
| `python -m pytest apps/api -q -o 'addopts='` | 通过 | `315 passed in 8.51s`，含已有抓取与 SSRF 回归。 |
| `npm --prefix apps/web run build` | 通过 | TypeScript 通过，Vite 转换 42 个模块并生成产物。 |
| 临时 DB 设置 `RDAP_ENABLED=true LLM_PROVIDER=stub`，`.\scripts\serve.ps1 -Provider fixture -Port 18150 -SkipBuild`，另起 shell 执行 `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18150` | 通过 | 16/16，`冒烟通过`。固定样本不发年龄查询，已有缓存可解释风险。 |
| `python scripts/ci-smoke.py http://127.0.0.1:18150` | 通过 | 15/15，`冒烟通过`。 |
| `Invoke-RestMethod http://127.0.0.1:18150/api/openapi.json` | 通过 | OpenAPI 生成成功，抓取依赖未混入查询参数。 |
| `git diff --check` 与本轮源文件、JSON 的凭据扫描 | 通过 | 无空白错误，`source_and_rdap_evidence_secret_scan=pass`。 |

| 类别 | 总数 | 年龄可得 / 未知 | <7 天 | <30 天 | <90 天 |
| --- | --- | --- | --- | --- | --- |
| OpenPhish feed 来源 | 20 | 18 / 2 | 3 | 4 | 4 |
| 公开参考域名 | 20 | 19 / 1 | 0 | 0 | 0 |

在已可得年龄的样本中，按现有候选规则和风险阈值，年龄增量 0.10、0.15 未新增标记，0.20 新增标记 1 个 feed 来源，参考域名均为 0。参考域名都较老，因此不能用这批数据估计新注册正常站点的误报率。

校准逐域允许 12 秒用于收集数据，并按至少 1.1 秒间隔启动，遵守 RDAP.org 引导服务的限速。线上搜索仍采用整批 4 秒预算，因此 37/40 的采集覆盖率不能解释为线上首屏覆盖率。正文页面均未访问。[服务说明](https://about.rdap.org/)

## 5 关键决策

- 批次计时覆盖信号收集，而非给每个域名轮流四秒。部分已完成结果可使用，未完成结果在本批跳过。
- 域名使用注册边界。托管平台的父域注册年龄仅代表父域，无法表示每个租户创建时间。
- 维持 30 天和 0.15。90 天在本批没有新增年龄命中，提升权重还缺新注册正常对照。

## 6 遗留与风险

- 当前 40 个域名是小型定向样本，feed 标签来自来源方，参考集合缺少新注册正常站点。
- 部分注册局没有给注册时间，未知单独计数。本批测了单次八域名预算，跨请求并发和服务端 429 仍需观察。
- 公开后缀表随核心依赖更新，当前请求路径使用包内数据。

## 7 交接

补充有出处的新注册正常域名后重放校准，观察 30 天阈值与 0.15 增量是否产生误报。已有样本可用 `--samples reports/assets/rdap-review/calibration.json` 重放；重新采样会取新的 feed 内容。

临时端口 18150 已停止，`data/rdap-calibration-review.db` 是独立派生缓存，正式书签库未用于本轮测试。待办已对齐到 `docs/进展与欠账.md`。

## 8 负载探针

```powershell
$env:PYTHONPATH=(Resolve-Path 'apps/api').Path
@'
import asyncio
import json
from pathlib import Path
import time

import httpx

from app.core.fetch import SafeFetcher
from app.core.rdap import DomainAgeStore, enrich
from app.schemas import Result

data = json.loads(Path("reports/assets/rdap-review/calibration.json").read_text(encoding="utf-8"))
for label, info in data["summary"].items():
    known = [row for row in data["rows"] if row["label"] == label and row["age_days"] is not None]
    info["newly_flagged_by_weight"] = {
        str(weight): sum(row["base_risk"] < 0.35 <= row["base_risk"] + weight for row in known if row["age_days"] < 30 and row["base_risk"] > 0)
        for weight in (0.1, 0.15, 0.2)
    }
Path("reports/assets/rdap-review/calibration.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def item(domain):
    return Result(id=domain, url="https://" + domain, display_url=domain, title="测试", snippet="", engine=["test"], score=0, risk=0.2)

async def main():
    store = DomainAgeStore(Path("data/rdap-calibration-review.db"))
    warm = [row["domain"].replace("[.]", ".") for row in data["rows"] if row["age_days"] is not None][:8]
    calls = []

    async def slow(request):
        calls.append(request)
        await asyncio.sleep(5)
        return httpx.Response(404)

    fetcher = SafeFetcher(timeout=10, transport=httpx.MockTransport(slow), resolver=lambda host: ["93.184.216.34"])
    start = time.perf_counter()
    await enrich([item(domain) for domain in warm], store, fetcher)
    warm_ms = round((time.perf_counter() - start) * 1000)
    assert not calls
    start = time.perf_counter()
    await enrich([item(f"rdap-load-review-{index}.com") for index in range(8)], store, fetcher)
    slow_ms = round((time.perf_counter() - start) * 1000)
    store.close()
    assert len(calls) == 4 and 3800 <= slow_ms < 4700
    result = {"warm_eight_ms": warm_ms, "slow_eight_ms": slow_ms, "network_started": len(calls), "network_queued_skipped": 4}
    Path("reports/assets/rdap-review/load.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    print(json.dumps(data["summary"], ensure_ascii=False))
asyncio.run(main())
'@ | python -X utf8 -
```

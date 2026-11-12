"""核验品牌入口表：逐条请求官网地址，记录状态、最终主机与标题。

用法：
  python scripts/verify-official.py [--json PATH] [--only brand] [--timeout 12] [--workers 8]

判定分三类：
  ok      2xx 且最终主机属于该品牌已声明主机 / 允许的跳转主机；
  blocked 401/403/429 或网络不可达（反爬、登录墙、地区限制）——身份无法用响应确认，
          不算入口表错误，但会单独计数并在资产里注明；
  fail    非声明 HTTPS 来源、未解析的 3xx、404/400/5xx——核验未通过，退出码 1；
          5xx 可能为临时故障，不单凭状态断言入口表错误。
本脚本只核验入口表本身，不验证页面内容是否为官方功能页。
输出默认写入 reports/assets/official-entries/verified.json。
退出码 0 表示没有 fail 项；blocked 需人工判断是否保留。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.core.official import table_snapshot  # noqa: E402

TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36 CleanSearch-OfficialCheck"
)


def fetch(url: str, timeout: float) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(200_000)
            status = response.status
            final = response.geturl()
    except urllib.error.HTTPError as exc:
        return {
            "status": exc.code,
            "final_url": exc.geturl(),
            "title": "",
            "ms": int((time.perf_counter() - started) * 1000),
            "error": f"HTTP {exc.code}",
        }
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return {
            "status": 0,
            "final_url": url,
            "title": "",
            "ms": int((time.perf_counter() - started) * 1000),
            "error": str(exc)[:200],
        }
    match = TITLE.search(body.decode("utf-8", "ignore"))
    title = re.sub(r"\s+", " ", match.group(1)).strip()[:120] if match else ""
    return {
        "status": status,
        "final_url": final,
        "title": title,
        "ms": int((time.perf_counter() - started) * 1000),
        "error": "",
    }


def host_of(url: str) -> str:
    try:
        from urllib.parse import urlsplit

        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def classify(result: dict, allowed_hosts: set[str]) -> tuple[str, str]:
    """先核对最终来源，再区分成功、受限和错误，受限不能掩盖跨站跳转。"""
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(result["final_url"])
        valid_origin = parts.scheme == "https" and parts.port in (None, 443) and parts.username is None
    except ValueError:
        valid_origin = False
    final_host = host_of(result["final_url"])
    if not valid_origin or final_host not in allowed_hosts:
        return "fail", f"跳到非声明 HTTPS 来源 {final_host}"
    status = result["status"]
    if 200 <= status < 300:
        return "ok", ""
    if status in (0, 401, 403, 429):
        return "blocked", "反爬 / 登录墙 / 网络不可达，未能用响应确认身份"
    return "fail", f"HTTP {status}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default=str(ROOT / "reports" / "assets" / "official-entries" / "verified.json"))
    parser.add_argument("--only", default="", help="只核验某个品牌 key")
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    rows = table_snapshot()
    if args.only:
        rows = [row for row in rows if row["brand"] == args.only]
    if not rows:
        print("没有匹配的入口行")
        return 1

    allowed: dict[str, set[str]] = {}
    for row in rows:
        allowed.setdefault(row["brand"], set()).update(row["allowed_hosts"])

    def work(row: dict) -> dict:
        url = f"https://{row['host']}{row['path']}"
        result = fetch(url, args.timeout)
        if result["status"] == 0:  # 并发下的瞬时连接失败重试一次
            time.sleep(1.0)
            result = fetch(url, args.timeout)
        final_host = host_of(result["final_url"])
        verdict, reason = classify(result, allowed[row["brand"]])
        return {
            **row,
            "url": url,
            "final_url": result["final_url"],
            "final_host": final_host,
            "status": status,
            "title": result["title"],
            "ms": result["ms"],
            "error": result["error"],
            "verdict": verdict,
            "ok": verdict == "ok",
            "reason": reason,
        }

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        checked = list(pool.map(work, rows))

    checked.sort(key=lambda row: (row["brand"], row["role"]))
    failures = [row for row in checked if row["verdict"] == "fail"]
    blocked = [row for row in checked if row["verdict"] == "blocked"]
    payload = {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "total": len(checked),
        "ok": len(checked) - len(failures) - len(blocked),
        "blocked": len(blocked),
        "failed": len(failures),
        "rows": checked,
    }
    target = Path(args.json)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    for row in checked:
        mark = {"ok": "OK ", "blocked": "BLK", "fail": "ERR"}[row["verdict"]]
        print(f"{mark} {row['brand']:<12} {row['role']:<8} {row['url']:<58} {row['status']:>3} {row['final_host']} {row['title'][:40]}")
    print(f"\n通过 {payload['ok']} / 受限 {payload['blocked']} / 失败 {payload['failed']}，共 {payload['total']}；明细 {target}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

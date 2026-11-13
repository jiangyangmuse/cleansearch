"""真实日常服务的少量导航/内容查询、缓存及总结引用验证。"""
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

OUT = Path(__file__).parent
BASE = "http://127.0.0.1:8000"


def search(query):
    request = Request(BASE + "/api/search", json.dumps({"q": query}).encode(), {"Content-Type": "application/json"})
    started = time.monotonic()
    with urlopen(request, timeout=60) as response:
        payload = json.load(response)
    groups = [item for group in payload["groups"].values() for item in group]
    entries = (payload.get("official") or {}).get("entries", [])
    assert payload["meta"]["provider"] == "searxng"
    assert len(entries) == payload["meta"]["official"] and len(groups) == payload["meta"]["total"]
    assert not ({entry["url"] for entry in entries} & {item["url"] for item in groups})
    assert len({item["id"] for item in groups + entries}) == len(groups + entries)
    assert all(entry["id"] and "snippet" in entry and "risk" in entry for entry in entries)
    print(json.dumps({"query": query, "cached": payload["meta"]["cached"], "official": len(entries),
                      "normal": len(groups), "seconds": round(time.monotonic()-started, 2),
                      "roles": [entry["role"] for entry in entries]}, ensure_ascii=False), flush=True)
    return payload


results = {}
try:
    results["brand_first"] = first = search("deepseek")
    assert first["official"] and first["official"]["key"] == "deepseek"
    results["brand_cached"] = warm = search("deepseek")
    assert warm["meta"]["cached"] and first["official"] == warm["official"]
    results["docs"] = docs = search("deepseek documentation")
    assert docs["official"] and docs["official"]["key"] == "deepseek"
    results["tutorial"] = tutorial = search("deepseek how to use")
    assert tutorial["official"] is None and tutorial["meta"]["official"] == 0
    assert tutorial["meta"]["total"] > 0
    (OUT / "search-live.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    events, event = [], ""
    started = time.monotonic()
    print("starting real-model fast summary", flush=True)
    with urlopen(BASE + "/api/summarize?sid=" + warm["meta"]["sid"] + "&mode=fast", timeout=60) as response:
        for raw in response:
            line = raw.decode("utf-8").strip()
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                events.append({"event": event, "data": json.loads(line[6:])})
                if event == "meta":
                    print(json.dumps({"summary_meta": events[-1]["data"]}, ensure_ascii=False), flush=True)
            if time.monotonic() - started > 90:
                raise TimeoutError("summary total budget 90s")
    summary = {"events": events, "seconds": round(time.monotonic()-started, 2)}
    (OUT / "summary-live.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    assert not [e for e in events if e["event"] == "error"], "real summary emitted error"
    assert any(e["event"] == "done" for e in events)
    with urlopen(BASE + "/api/health", timeout=3) as response:
        configured_model = json.load(response)["llm_model"]
    models = [e["data"]["model"] for e in events if e["event"] == "meta"]
    assert models == [configured_model] and models[0] != "stub-extractive", "configured model did not run"
    citations = [e["data"] for e in events if e["event"] == "cite"]
    declared = {item["id"]: item["url"] for group in warm["groups"].values() for item in group}
    declared.update({item["id"]: item["url"] for item in warm["official"]["entries"]})
    assert all(declared.get(cite["result_id"]) == cite["url"] for cite in citations)
    assert citations[0]["result_id"] == warm["official"]["entries"][0]["id"]
    text = "".join(e["data"]["t"] for e in events if e["event"] == "token")
    assert text.strip() and any(f"[{cite['i']}]" in text for cite in citations)
    print(json.dumps({"summary_done": True, "citations": len(citations), "text_chars": len(text),
                      "seconds": summary["seconds"], "first_citation_is_official": True}, ensure_ascii=False), flush=True)
except Exception:
    (OUT / "search-live.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    raise

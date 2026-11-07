"""Regression checks for acceptance denominators and incomplete SSE evidence."""
from __future__ import annotations

import importlib.util
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_expansion_reports_all_queries_separately_from_alias_subset():
    tool = load_script("eval-expansion")
    metric = {"hit10": True, "strong": False, "first_rank": 1}
    rows = [{"has_expansion": index < 12, "baseline": metric, "ranking": metric,
             "rewrite": metric if index < 12 else None} for index in range(40)]
    result = tool.evaluation(rows, {})
    assert result["summary"]["rewrite"]["cases"] == 12
    assert result["all_summary"]["rewrite"]["cases"] == 40
    assert result["controls_summary"]["rewrite"]["cases"] == 28
    assert result["all_summary"]["rewrite"]["hit10"] == 40
    assert result["all_summary"]["baseline"]["success"] is None


def test_expansion_failure_stays_in_denominator_and_mrr():
    tool = load_script("eval-expansion")
    rows = [{"has_expansion": True, "baseline": value} for value in (
        {"hit10": True, "strong": False, "first_rank": 2, "ok": True},
        {"hit10": False, "strong": False, "first_rank": None, "ok": False})]
    result = tool.summarize(rows, "baseline")
    assert result["cases"] == 2 and result["success"] == 1
    assert result["mrr10"] == 0.25 and result["mean_first_rank"] == 2


def test_summary_stream_without_done_or_with_wrong_citations_fails():
    tool = load_script("eval-summary")
    results = [{"id": "result-1", "url": "https://example.com/"}]
    row = {"meta": {"sid": "sid", "mode": "fast", "degraded": False, "sources": 1},
           "done": {"mode": "fast", "partial": False, "tokens": 1}, "token_chunks": 1, "text": "Claim [1]",
           "citations": [{"i": 1, "result_id": "result-1", "url": "https://example.com/"}]}
    assert tool.assess(row, results, "sid", "fast")["passed"]
    assert not tool.assess({**row, "done": None}, results, "sid", "fast")["passed"]
    assert not tool.assess({**row, "text": "Claim [99]"}, results, "sid", "fast")["passed"]
    assert not tool.assess({**row, "token_chunks": 0}, results, "sid", "fast")["passed"]
    row["citations"][0]["url"] = "https://wrong.example/"
    assert not tool.assess(row, results, "sid", "fast")["passed"]


def test_sse_does_not_accept_truncated_last_event():
    tool = load_script("eval-summary")
    assert list(tool.events(io.BytesIO(b'event: done\ndata: {"tokens": 1}\n'))) == []
    assert list(tool.events(io.BytesIO(b'event: done\ndata: {"tokens": 1}\n\n'))) == [("done", {"tokens": 1})]


def test_rdap_old_unknown_and_unprovenanced_controls_do_not_close_new_site_gate():
    tool = load_script("eval-rdap")
    rows = [
        {"label": "reference", "age_days": 5000, "base_risk": 0.2},
        {"label": "reference", "age_days": None, "base_risk": 0.2},
        {"label": "reference", "age_days": 5, "base_risk": 0.2},
        {"label": "reference", "age_days": 10, "base_risk": 0.2, "provenance": "https://example.com/project"},
    ]
    summary = tool.summarize_rows(rows)
    assert summary["reference"]["unknown"] == 1
    assert summary["fresh_normal_controls"]["age_known_under_30d"] == 2
    assert summary["fresh_normal_controls"]["with_recorded_provenance"] == 1
    assert summary["fresh_normal_controls"]["reference_provenance_missing"] == 3

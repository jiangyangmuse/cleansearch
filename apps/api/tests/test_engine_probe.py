"""探测矩阵只认可指定引擎的来源，防止静默默认聚合制造假阳性。"""

import importlib.util
import io
import json
from pathlib import Path

import pytest


@pytest.mark.parametrize(("payload", "count", "ok"), [
    ({"results": [{"engine": "bing"}]}, 0, False),
    ({"results": [{"engines": ["google"]}, {"engine": "bing"}]}, 1, True),
    ({"results": []}, 0, False),
    ({"results": "invalid"}, None, False),
])
def test_probe_verifies_requested_source(monkeypatch, payload, count, ok):
    path = Path(__file__).resolve().parents[3] / "scripts" / "probe-engines.py"
    spec = importlib.util.spec_from_file_location("probe_engines", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(json.dumps(payload).encode()))
    result = module.probe("http://local.test", "google", "python")
    assert result["ok"] is ok
    assert result.get("count") == count


def test_probe_skips_unloaded_engine_without_search_request(monkeypatch):
    path = Path(__file__).resolve().parents[3] / "scripts" / "probe-engines.py"
    spec = importlib.util.spec_from_file_location("probe_engines", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *args, **kwargs: pytest.fail("未加载引擎不应触发默认聚合"))
    row = module.probe("http://local.test", "startpage", "python", loaded={"bing"})
    assert row["skipped"] == "not_loaded" and not row["ok"]


def test_malformed_catalog_is_unknown_not_empty_catalog(monkeypatch):
    path = Path(__file__).resolve().parents[3] / "scripts" / "probe-engines.py"
    spec = importlib.util.spec_from_file_location("probe_engines", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(b'{"engines": "invalid"}'))
    assert module.loaded_engines("http://local.test") is None

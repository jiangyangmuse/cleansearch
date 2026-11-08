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

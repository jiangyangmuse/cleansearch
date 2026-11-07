"""测试固定使用 fixture 上游 + 临时前端产物，不依赖 Docker / 网络。"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

_STATIC = Path(tempfile.mkdtemp(prefix="cs-static-"))
(_STATIC / "assets").mkdir(parents=True, exist_ok=True)
(_STATIC / "index.html").write_text(
    "<!doctype html><html><body><div id=\"root\">spa-index</div>"
    "<script type=\"module\" src=\"/assets/app.js\"></script></body></html>",
    encoding="utf-8",
)
(_STATIC / "assets" / "app.js").write_text("console.log('spa');", encoding="utf-8")

os.environ["SEARCH_PROVIDER"] = "fixture"
os.environ["LLM_PROVIDER"] = "stub"
os.environ["LLM_STUB_DELAY"] = "0"
os.environ["WEB_DIST"] = str(_STATIC)
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="cs-db-")) / "cs.db")
# 默认关缓存：用例之间互不污染；缓存专项用例自己打开
os.environ["CACHE_ENABLED"] = "false"
os.environ["API_TOKEN_PATH"] = str(Path(tempfile.mkdtemp(prefix="cs-token-")) / "api-token.txt")
# 默认关熔断：单个用例里的上游失败不应该冷却整个测试会话
os.environ["BREAKER_ENABLED"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.config import get_settings  # noqa: E402

get_settings.cache_clear()


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


@pytest.fixture()
def static_dir() -> Path:
    return _STATIC

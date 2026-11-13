"""本轮免费实测/原始 fixture 冒烟隔离实例，付费能力硬关闭。"""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = "--fixture" in sys.argv
DATA = ROOT / "data/bing-retrieval-review" / ("fixture" if FIXTURE else "live")
DATA.mkdir(parents=True, exist_ok=True)
for name, value in {
    "SEARCH_PROVIDER": "fixture" if FIXTURE else "searxng", "SEARXNG_URL": "http://127.0.0.1:8888",
    "LLM_PROVIDER": "stub", "LLM_STUB_DELAY": "0", "DB_PATH": str(DATA / "cs.db"),
    "API_TOKEN_PATH": str(DATA / "token.txt"), "FAVICON_DIR": str(DATA / "favicons"),
    "FEED_OUTPUT_PATH": str(DATA / "feed.txt"), "PAID_FALLBACK": "false",
    "SERPER_API_KEY": "", "BRAVE_API_KEY": "", "RDAP_ENABLED": "false",
    "BREAKER_ENABLED": "false", "CACHE_ENABLED": "true", "WEB_DIST": str(ROOT / "apps/web/dist"),
}.items():
    os.environ[name] = value
sys.path.insert(0, str(ROOT / "apps/api"))
from app.main import app
import uvicorn
uvicorn.run(app, host="127.0.0.1", port=18178 if FIXTURE else 18177)

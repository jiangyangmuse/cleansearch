"""隔离 fixture 服务，仅用于本轮浏览器和冒烟，不读正式库或调用模型。"""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SMOKE = "--smoke" in sys.argv
DATA = ROOT / "data" / "official-entry-review" / ("smoke" if SMOKE else "browser")
DATA.mkdir(parents=True, exist_ok=True)
for key, value in {
    "SEARCH_PROVIDER": "fixture", "LLM_PROVIDER": "stub", "LLM_STUB_DELAY": "0",
    "DB_PATH": str(DATA / "review.db"), "CACHE_ENABLED": "true", "RDAP_ENABLED": "false",
    "API_TOKEN_PATH": str(DATA / "token.txt"), "FAVICON_DIR": str(DATA / "favicons"),
    "FEED_OUTPUT_PATH": str(DATA / "feed.txt"), "PAID_FALLBACK": "false",
    "WEB_DIST": str(ROOT / "apps/web/dist"), "BREAKER_ENABLED": "false",
}.items():
    os.environ[key] = value
sys.path.insert(0, str(ROOT / "apps/api"))
from app.core.aggregator import get_aggregator
from app.main import app
import uvicorn

get_aggregator()._fixture._hit = {"results": [
    {"url": "https://www.deepseek.com/", "title": "DeepSeek · 官网与产品入口", "content": "官方介绍与产品信息", "engine": "google"},
    {"url": "https://chat.deepseek.com/", "title": "DeepSeek Chat", "content": "官方聊天服务", "engine": "bing"},
    {"url": "https://api-docs.deepseek.com/", "title": "DeepSeek API 开发文档与完整使用参考", "content": "官方 API 文档摘要", "engine": "google"},
    {"url": "https://platform.deepseek.com/", "title": "DeepSeek 开放平台", "content": "官方开放平台与账户管理", "engine": "yahoo"},
    {"url": "https://en.wikipedia.org/wiki/DeepSeek", "title": "DeepSeek", "content": "第三方百科参考", "engine": "bing"},
    {"url": "https://www.deepseek.com.example.org/", "title": "DeepSeek 官网", "content": "未通过品牌表匹配的域名", "engine": "yahoo"},
]} if not SMOKE else get_aggregator()._fixture._hit
uvicorn.run(app, host="127.0.0.1", port=18176 if SMOKE else 18175)

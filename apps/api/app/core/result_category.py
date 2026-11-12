"""按落地页类型分类搜索结果。"""

from urllib.parse import urlsplit


def result_category(url: str, title: str):
    parts = urlsplit(url)
    host = parts.hostname or ""
    path = parts.path.lower().rstrip("/")

    def on(domain: str) -> bool:
        return host == domain or host.endswith("." + domain)

    if (
        on("wikipedia.org")
        or on("prts.wiki")
        or host in ("baike.baidu.com", "wapbaike.baidu.com")
        or (on("fandom.com") and path.startswith("/wiki/"))
        or (host == "www.baike.com" and path.startswith("/wiki/"))
    ):
        return "encyclopedia"
    if (
        (on("youtube.com") and (path in ("/watch", "/playlist") or path.startswith("/shorts/")))
        or (host == "youtu.be" and bool(path))
        or (on("bilibili.com") and path.startswith(("/video/", "/bangumi/play/")))
        or (host == "v.qq.com" and path.startswith(("/x/page/", "/x/cover/")))
        or (on("youku.com") and path.startswith("/v_show/"))
        or (on("douyin.com") and path.startswith("/video/"))
        or (on("tiktok.com") and "/video/" in path)
        or (host == "vimeo.com" and path.lstrip("/").isdigit())
    ):
        return "video"
    if (
        (host == "apps.apple.com" and "/app/" in path)
        or (host == "play.google.com" and path == "/store/apps/details")
        or ((on("taptap.cn") or on("taptap.com")) and "/app/" in path)
        or (host == "store.steampowered.com" and path.startswith("/app/"))
        or (host == "www.nexon.com" and path.startswith("/launcher"))
        or path.endswith((".apk", ".exe", ".msi", ".dmg", ".ipa"))
        or ("下载" in title and any(segment in {"download", "downloads"} for segment in path.split("/")))
    ):
        return "download"
    return None

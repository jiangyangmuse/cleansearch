"""M1 安全过滤：黑名单匹配、风险分档、热加载。"""

from __future__ import annotations

from pathlib import Path

from app.core.safety import BLOCK_THRESHOLD, SUSPICIOUS_THRESHOLD, Blocklist, SafetyScorer


def make_blocklist(tmp_path: Path, text: str) -> Blocklist:
    path = tmp_path / "blocklist.txt"
    path.write_text(text, encoding="utf-8")
    return Blocklist(path)


def test_domain_and_subdomain_blocked(tmp_path: Path) -> None:
    scorer = SafetyScorer(make_blocklist(tmp_path, "evil.test\n# 注释\n"))
    assert scorer.evaluate("https://evil.test/login").blocked
    assert scorer.evaluate("http://www.evil.test/a").blocked
    assert not scorer.evaluate("https://not-evil.test/a").blocked


def test_exact_url_rule(tmp_path: Path) -> None:
    scorer = SafetyScorer(make_blocklist(tmp_path, "https://tracker.example.test/scam\n"))
    assert scorer.evaluate("https://tracker.example.test/scam").blocked
    assert scorer.evaluate("HTTPS://Tracker.Example.Test:443/scam/#jump").blocked
    assert not scorer.evaluate("https://tracker.example.test/other").blocked
    assert not scorer.evaluate("https://tracker.example.test/scam?id=other").blocked
    assert not scorer.evaluate("https://tracker.example.test:8443/scam").blocked


def test_missing_file_degrades_to_empty(tmp_path: Path) -> None:
    scorer = SafetyScorer(Blocklist(tmp_path / "nope.txt"))
    assert scorer.blocklist.size == 0
    assert scorer.evaluate("https://example.com/a").blocked is False


def test_hot_reload_picks_up_new_rules(tmp_path: Path) -> None:
    path = tmp_path / "blocklist.txt"
    path.write_text("", encoding="utf-8")
    scorer = SafetyScorer(Blocklist(path))
    assert not scorer.evaluate("https://late.test/x").blocked
    path.write_text("late.test\n", encoding="utf-8")
    assert scorer.evaluate("https://late.test/x").blocked


def test_single_suspicious_tld_is_low_risk(tmp_path: Path) -> None:
    scorer = SafetyScorer(make_blocklist(tmp_path, ""))
    report = scorer.evaluate("https://shop.top/buy")
    assert report.blocked is False
    assert report.risk == 0.15                      # 单一信号不越过 0.35 标记线
    assert report.risk < SUSPICIOUS_THRESHOLD
    assert any(".top" in reason for reason in report.reasons)


def test_ip_literal_and_long_path(tmp_path: Path) -> None:
    scorer = SafetyScorer(make_blocklist(tmp_path, ""))
    report = scorer.evaluate("http://198.51.100.7/a1b2c3d4e5f6g7h8i9j0k1l2/download")
    assert "IP 直连" in report.reasons
    assert report.risk == 0.10


def test_idn_and_deep_subdomain_stack_risk(tmp_path: Path) -> None:
    scorer = SafetyScorer(make_blocklist(tmp_path, ""))
    report = scorer.evaluate("https://login.secure.verify.xn--80ak6aa92e.top/pay")
    assert report.risk >= SUSPICIOUS_THRESHOLD
    assert report.blocked is False
    assert set(report.reasons) >= {"IDN 编码域名", "可疑顶级域 .top", "子域层级过多"}


def test_clean_url_has_zero_risk(tmp_path: Path) -> None:
    scorer = SafetyScorer(make_blocklist(tmp_path, ""))
    report = scorer.evaluate("https://docs.python.org/3/library/asyncio.html")
    assert report.risk == 0.0 and report.blocked is False


def test_threshold_constant_is_documented_value() -> None:
    assert BLOCK_THRESHOLD == 0.6

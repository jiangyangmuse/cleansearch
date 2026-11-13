"""去重强度：off / normal / strict 三种行为。"""

from __future__ import annotations

from app.core.normalize import apply_dedupe
from app.schemas import Result


def _item(index: int, url: str, title: str) -> Result:
    return Result(id="in_%d" % index, url=url, display_url=url, title=title, engine=["google"])


def test_dedupe_off_keeps_everything() -> None:
    items = [
        _item(1, "https://a.test/x?utm_source=1", "Python 教程"),
        _item(2, "https://a.test/x", "Python 教程"),
        _item(3, "https://b.test/y", "Python 教程"),
    ]
    kept, removed = apply_dedupe(items, "off")
    assert len(kept) == 3 and removed == 0
    assert [item.id for item in kept] == ["r_1", "r_2", "r_3"]


def test_dedupe_normal_merges_canonical_url() -> None:
    items = [
        _item(1, "https://a.test/x?utm_source=1", "甲"),
        _item(2, "https://a.test/x", "乙"),
        _item(3, "https://b.test/y", "丙"),
    ]
    kept, removed = apply_dedupe(items, "normal")
    assert len(kept) == 2 and removed == 1


def test_dedupe_strict_also_merges_same_title() -> None:
    items = [
        _item(1, "https://a.test/x", "Python 入门教程"),
        _item(2, "https://b.test/y", "Python 入门教程"),
        _item(3, "https://c.test/z", "完全不同的标题"),
    ]
    kept, removed = apply_dedupe(list(items), "strict")
    assert len(kept) == 2 and removed == 1
    kept_normal, removed_normal = apply_dedupe(list(items), "normal")
    assert len(kept_normal) == 3 and removed_normal == 0

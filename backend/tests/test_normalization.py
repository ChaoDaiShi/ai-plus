"""normalization 单元测试（任务 §26-B）：空/重复/无意义/非法星级/合法评论。"""

from types import SimpleNamespace

from app.agent.nodes.normalization import distribution, normalize_one


def test_empty_text_excluded():
    assert normalize_one("   ", 5) == "empty_text"
    assert normalize_one("", 5) == "empty_text"


def test_duplicate_semantics():
    # 重复剔除由 content_hash 在节点内完成；normalize_one 不负责重复
    assert normalize_one("ok", 5) == "meaningless"


def test_meaningless_short_reviews_excluded():
    for text in ("ok", "good", "nice", "great", "fine", "fast", "meh"):
        assert normalize_one(text, 4) == "meaningless", text


def test_short_with_defect_keyword_kept():
    # 短评含缺陷信息不能仅按长度删除（技术方案 §5.2）
    assert normalize_one("Broke", 1) is None
    assert normalize_one("Leaked oil", 2) is None


def test_short_without_defect_excluded():
    assert normalize_one("It's fine", 4) == "too_short"


def test_invalid_rating_excluded():
    assert normalize_one("Great chair overall quality", 6) == "invalid_rating"
    assert normalize_one("Great chair overall quality", 0) == "invalid_rating"
    assert normalize_one("Great chair overall quality", None) == "invalid_rating"
    assert normalize_one("Great chair overall quality", "abc") == "invalid_rating"


def test_valid_review_kept():
    assert normalize_one("The armrest snapped after two weeks.", 1) is None
    assert normalize_one("Good value for money.", 4) is None


def test_distribution_counts():
    reviews = [
        SimpleNamespace(rating=1, language="en", reviewed_at=__import__("datetime").date(2026, 8, 1)),
        SimpleNamespace(rating=2, language="de", reviewed_at=__import__("datetime").date(2026, 8, 9)),
        SimpleNamespace(rating=5, language=None, reviewed_at=None),
    ]
    rating_dist, language_dist, month_dist = distribution(reviews)
    assert rating_dist == {"1": 1, "2": 1, "3": 0, "4": 0, "5": 1}
    assert language_dist == {"en": 1, "de": 1, "und": 1}
    assert month_dist == {"2026-08": 2}

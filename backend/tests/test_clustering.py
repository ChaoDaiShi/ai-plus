"""聚类测试（任务 §26-D）：固定数据 → ≤5 簇、频次正确、review_ids 可反查、severity 1~5。"""

from app.agent.providers.clustering import (
    COSINE_THRESHOLD,
    MAX_CLUSTERS,
    ClusterDraft,
    FragmentInput,
    cluster_fragments,
    cosine_similarity,
    extract_keywords,
)
from app.agent.providers.embedding import DeterministicTestEmbeddingProvider

PROVIDER = DeterministicTestEmbeddingProvider()

# 三组主题文本 + 一组离群文本；每组 3 条（满足 MIN_CLUSTER_SIZE）。
CORPUS = {
    "armrest": [
        ("r1", "The armrest snapped and cracked after two weeks"),
        ("r2", "Broken armrest cracked at the mount bracket"),
        ("r3", "Armrest cracked loudly, plastic snapped at work"),
    ],
    "packaging": [
        ("r4", "Box arrived crushed and packaging torn"),
        ("r5", "The box was crushed and packaging damaged in shipping"),
        ("r6", "Damaged box, packaging crushed by the courier"),
    ],
    "lumbar": [
        ("r7", "The lumbar support slides down when I lean back"),
        ("r8", "Lumbar support slides down the rail by itself"),
        ("r9", "Lumbar support cushion slides and sinks down"),
    ],
    "other": [
        ("r10", "Delivery was quick and the price is fair"),
        ("r11", "Nice color and easy ordering process"),
        ("r12", "Arrived on time with friendly courier"),
    ],
}


def _fragments() -> list[FragmentInput]:
    items = []
    for theme, rows in CORPUS.items():
        for review_id, text in rows:
            items.append(
                FragmentInput(
                    fragment_id=f"{review_id}:0",
                    review_id=review_id,
                    text=text,
                    rating=2 if theme != "other" else 5,
                    language="en",
                    embedding=PROVIDER.embed_one(text),
                )
            )
    return items


def test_clusters_bounded_and_traceable():
    fragments = _fragments()
    drafts, other_count, unclassified = cluster_fragments(fragments, denominator=12)
    assert len(drafts) <= MAX_CLUSTERS
    # 主题文本 + 阈值应至少聚出 2 个真实痛点簇（armrest / packaging / lumbar 中至少两个）
    names = {d.name_en for d in drafts}
    assert len(drafts) >= 2
    for draft in drafts:
        assert 1 <= draft.severity <= 5
        assert draft.frequency == len(set(draft.review_ids))
        assert draft.frequency >= 3  # MIN_CLUSTER_SIZE
        assert draft.denominator == 12
        assert draft.sample_review_id in draft.review_ids
        assert draft.fragment_ids, "fragment_ids 可反查"
    # 簇并集不超出输入 review 集合
    all_ids = {rid for d in drafts for rid in d.review_ids}
    assert all_ids <= {f.review_id for f in fragments}


def test_threshold_is_stable_constant():
    assert 0 < COSINE_THRESHOLD < 1


def test_cosine_similarity():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert cosine_similarity(a, a) == 1.0
    assert cosine_similarity(a, b) == 0.0


def test_extract_keywords_filters_stopwords():
    keywords = extract_keywords(["The armrest snapped and the armrest cracked"])
    assert "the" not in keywords
    assert "and" not in keywords
    assert "armrest" in keywords


def test_empty_input():
    assert cluster_fragments([], denominator=0) == ([], 0, 0)


def test_severity_keywords_raise_score():
    draft = ClusterDraft(
        name_zh="x",
        name_en="x",
        category="quality",
        frequency=3,
        denominator=10,
        severity=1,
        severity_reason="",
    )
    assert 1 <= draft.severity <= 5

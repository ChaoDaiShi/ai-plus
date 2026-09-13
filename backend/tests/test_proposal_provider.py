"""proposal Provider 测试（任务 §26-E）：两栏齐全、cluster/review 引用有效。"""

import asyncio

from app.agent.providers.clustering import ClusterDraft
from app.agent.providers.proposal import (
    RuleBasedProposalProvider,
    get_proposal_provider,
)


def _cluster(key: str, name_en: str, keywords: list[str], review_ids: list[str]) -> ClusterDraft:
    return ClusterDraft(
        name_zh=name_en,
        name_en=name_en,
        category="quality",
        frequency=len(review_ids),
        denominator=50,
        severity=4,
        severity_reason="测试",
        keywords=keywords,
        review_ids=review_ids,
        fragment_ids=[f"{rid}:0" for rid in review_ids],
        sample_text="sample",
        sample_review_id=review_ids[0],
    )


def _clusters() -> list[ClusterDraft]:
    return [
        _cluster("cluster_0", "Armrest breakage", ["armrest", "snapped", "cracked"], ["r1", "r2", "r3"]),
        _cluster("cluster_1", "Shipping package damage", ["box", "crushed", "carton"], ["r4", "r5", "r6"]),
        _cluster("cluster_2", "Unclear assembly instructions", ["instructions", "confusing", "manual"], ["r7", "r8"]),
    ]


def test_rule_based_generates_both_tracks():
    proposals = asyncio.run(RuleBasedProposalProvider().generate(_clusters()))
    tracks = {p.track_type for p in proposals}
    assert "BODY_OPTIMIZATION" in tracks
    assert "PACKAGING_FULFILLMENT" in tracks


def test_targets_and_evidence_come_from_clusters():
    clusters = _clusters()
    valid_keys = {f"cluster_{i}" for i in range(len(clusters))}
    valid_reviews = {rid for c in clusters for rid in c.review_ids}
    for proposal in asyncio.run(RuleBasedProposalProvider().generate(clusters)):
        assert proposal.target_cluster_keys, "target_cluster_ids 非空"
        assert set(proposal.target_cluster_keys) <= valid_keys
        assert proposal.evidence_review_ids, "evidence_review_ids 非空"
        assert set(proposal.evidence_review_ids) <= valid_reviews
        for key in proposal.target_cluster_keys:
            cluster = clusters[int(key.split("_")[1])]
            assert set(proposal.evidence_review_ids) <= set(cluster.review_ids)


def test_unmatched_cluster_yields_no_proposal():
    cluster = _cluster("cluster_0", "Totally unrelated theme", ["color", "style"], ["r9", "r10"])
    proposals = asyncio.run(RuleBasedProposalProvider().generate([cluster]))
    assert proposals == []


def test_empty_clusters():
    assert asyncio.run(RuleBasedProposalProvider().generate([])) == []


def test_factory_defaults_to_rule_based(monkeypatch):
    monkeypatch.setattr("app.config.settings.anthropic_api_key", "")
    assert get_proposal_provider().name == "rule_based"

"""proposal 节点：基于簇草稿生成双栏建议（BODY/PACKAGING）。

证据引用由 Provider 从簇内真实评论注入，本节点不做任何内容创作之外的
数据变更；恢复路径从本节点 output_summary 重载草稿。
"""

from app.agent.nodes.clustering import dict_to_draft
from app.agent.nodes.common import dump_summary
from app.agent.providers.proposal import (
    PROPOSAL_PIPELINE_VERSION,
    get_proposal_provider,
)


async def run(session_factory, state: dict) -> tuple[dict, dict]:
    clusters = [dict_to_draft(c) for c in state.get("clusters", [])]
    provider = get_proposal_provider()
    drafts = await provider.generate(clusters)

    proposal_dicts = []
    for index, draft in enumerate(drafts):
        proposal_dicts.append(
            {
                "key": f"proposal_{index}",
                "track_type": draft.track_type,
                "title_zh": draft.title_zh,
                "title_en": draft.title_en,
                "problem": draft.problem,
                "recommendation": draft.recommendation,
                "target_cluster_keys": draft.target_cluster_keys,
                "expected_effect": draft.expected_effect,
                "cost_level": draft.cost_level,
                "evidence_review_ids": draft.evidence_review_ids,
            }
        )

    body_count = sum(1 for p in proposal_dicts if p["track_type"] == "BODY_OPTIMIZATION")
    packaging_count = sum(
        1 for p in proposal_dicts if p["track_type"] == "PACKAGING_FULFILLMENT"
    )
    summary = {
        "proposal_version": PROPOSAL_PIPELINE_VERSION,
        "provider": provider.name,
        "proposals": len(proposal_dicts),
        "body": body_count,
        "packaging": packaging_count,
        "drafts": proposal_dicts,
    }
    updates = {"proposals": proposal_dicts}
    return dump_summary(summary), updates

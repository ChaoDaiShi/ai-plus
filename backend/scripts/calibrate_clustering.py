"""离线聚类校准（开发用）：demo 数据集 → 片段 → 向量 → 不同阈值聚类效果。"""

import asyncio
import json
import sys
from pathlib import Path

from app.agent.nodes.embedding import split_fragments
from app.agent.providers.clustering import (
    COSINE_THRESHOLD,
    FragmentInput,
    cluster_fragments,
)
from app.agent.providers.embedding import DeterministicTestEmbeddingProvider

DEMO = Path(__file__).resolve().parents[1] / "app" / "demo_data" / "B08N5WRWNW.json"


async def main():
    payload = json.loads(DEMO.read_text(encoding="utf-8"))
    provider = DeterministicTestEmbeddingProvider()
    fragments: list[FragmentInput] = []
    for review in payload["reviews"]:
        if review["rating"] > 3:
            continue
        text = f"{review['title']}. {review['body']}" if review.get("title") else review["body"]
        for start, end, piece in split_fragments(text):
            fragments.append(
                FragmentInput(
                    fragment_id=f"{review['review_id']}:{start}",
                    review_id=review["review_id"],
                    text=piece,
                    rating=review["rating"],
                    language=review.get("language"),
                    embedding=provider.embed_one(piece),
                )
            )
    # 去重 review 保持与 DB 相同口径
    seen = set()
    unique = []
    for f in fragments:
        if f.review_id in seen:
            continue
        unique.append(f)
    for threshold in [0.25, 0.3, 0.35, 0.4, 0.45, 0.5]:
        import app.agent.providers.clustering as cl

        cl.COSINE_THRESHOLD = threshold
        drafts, other, unclassified = cluster_fragments(unique, denominator=len(unique))
        print(f"--- threshold={threshold}: clusters={len(drafts)} other={other} unclassified={unclassified}")
        for d in drafts[:8]:
            print(f"    freq={d.frequency:2d} sev={d.severity} [{d.category:12s}] {d.name_en:42s} kw={','.join(d.keywords[:5])}")
    _ = COSINE_THRESHOLD


asyncio.run(main())

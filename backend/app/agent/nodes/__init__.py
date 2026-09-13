"""P0 业务节点注册表：顺序、展示元数据与进度映射的唯一事实来源。

app.worker.nodes 从这里 re-export NODE_ORDER（任务 §3：结束 stub 状态）。
"""

NODE_ORDER: tuple[str, ...] = (
    "ingestion",
    "normalization",
    "embedding",
    "clustering",
    "proposal",
    "evidence_validation",
    "publish",
)

# 任务 §16 的节点进度映射。
NODE_PROGRESS: dict[str, int] = {
    "ingestion": 10,
    "normalization": 25,
    "embedding": 45,
    "clustering": 65,
    "proposal": 80,
    "evidence_validation": 92,
    "publish": 100,
}

# 前端展示用的节点名（zh/en）与说明。
NODE_DISPLAY: dict[str, dict[str, str]] = {
    "ingestion": {
        "name_zh": "评论采集",
        "name_en": "Review ingestion",
        "desc_zh": "按 ASIN 与时间窗采集评论并落数据快照",
        "desc_en": "Collect reviews for the ASIN window into a data snapshot",
    },
    "normalization": {
        "name_zh": "评论清洗",
        "name_en": "Normalization",
        "desc_zh": "去重、过滤无效评论并生成覆盖统计",
        "desc_en": "Dedupe, filter and compute coverage statistics",
    },
    "embedding": {
        "name_zh": "片段向量化",
        "name_en": "Embedding",
        "desc_zh": "评论片段提取并生成 1024 维向量",
        "desc_en": "Extract fragments and embed into 1024-dim vectors",
    },
    "clustering": {
        "name_zh": "痛点聚类",
        "name_en": "Clustering",
        "desc_zh": "余弦阈值聚类并选出 Top 5 痛点",
        "desc_en": "Cosine threshold clustering for top pain points",
    },
    "proposal": {
        "name_zh": "双栏建议",
        "name_en": "Dual-column proposals",
        "desc_zh": "生成本体优化与包装履约两栏改款建议",
        "desc_en": "Generate body and packaging reform proposals",
    },
    "evidence_validation": {
        "name_zh": "证据校验",
        "name_en": "Evidence validation",
        "desc_zh": "校验建议引用的簇与评论真实存在",
        "desc_en": "Verify all referenced clusters and reviews exist",
    },
    "publish": {
        "name_zh": "报告发布",
        "name_en": "Publish report",
        "desc_zh": "持久化不可变分析报告",
        "desc_en": "Persist the immutable analysis report",
    },
}

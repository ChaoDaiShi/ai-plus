"""痛点聚类（任务 §9-§10）：余弦阈值 leader 聚类 + 确定性严重度与命名。

技术方案 §5.2 的基线方法：按稳定顺序将片段分配到满足余弦相似度阈值的
最近簇中心，不满足则建立候选簇；簇过小归入未归类。严重度由低星占比、
频率与严重词的确定性规则计算，禁止 LLM 自由生成；命名由关键词映射表
确定性给出（LLM 命名留作后续增强，且不得改写频次/严重度）。
"""

import math
import re
from dataclasses import dataclass, field

from app.agent.providers.embedding import tokenize_for_embedding

CLUSTERING_VERSION = "leader-cosine-v1"
COSINE_THRESHOLD = 0.35
MIN_CLUSTER_SIZE = 3
MAX_CLUSTERS = 5

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# 严重词与风险词：命中提升严重度（任务 §9 的确定性示例词表）。
SEVERE_WORDS = frozenset(
    """broken crack cracked snapped snap sheared fractured shattered dangerous
    injury injured hurt unsafe sharp failed refund unusable broke""".split()
)
RISK_WORDS = frozenset(
    """dangerous injury injured hurt unsafe jagged tilted tilted dangerously""".split()
)

# 关键词 → 品类（api.md §5.1 category 枚举）。
_CATEGORY_RULES: list[tuple[tuple[str, ...], str]] = [
    (("armrest", "base", "cylinder", "leg", "mount", "stem", "crack", "cracked",
      "snap", "snapped", "broken", "broke", "sheared", "fractured"), "quality"),
    (("manual", "instructions", "diagram", "assembly", "assemble", "step"), "instructions"),
    (("box", "carton", "packaging", "shipping", "transit", "courier", "crushed",
      "styrofoam", "cushioning"), "packaging"),
    (("missing", "screw", "screws", "washers", "allen"), "accessory"),
    (("small", "narrow", "short", "tight"), "size"),
    (("lumbar", "wobble", "squeak", "squeaky", "smell", "odor", "sinks", "slide",
      "slides", "caster", "casters", "wheel", "wheels", "squeaks"), "function"),
]

# 关键词对 → 确定性命名（zh/en）。命中顺序即优先级。
_NAME_RULES: list[tuple[frozenset[str], str, str]] = [
    (frozenset({"armrest", "broken"}), "扶手断裂", "Armrest breakage"),
    (frozenset({"armrest", "cracked"}), "扶手断裂", "Armrest breakage"),
    (frozenset({"armrest", "snapped"}), "扶手断裂", "Armrest breakage"),
    (frozenset({"armrest", "crack"}), "扶手开裂", "Armrest cracking"),
    (frozenset({"armrest", "wobble"}), "扶手松动", "Loose armrests"),
    (frozenset({"lumbar", "slides"}), "腰托支撑下滑", "Lumbar support slippage"),
    (frozenset({"lumbar", "slide"}), "腰托支撑下滑", "Lumbar support slippage"),
    (frozenset({"lumbar", "support"}), "腰托支撑失效", "Lumbar support failure"),
    (frozenset({"squeak"}), "异响噪音", "Squeaking noises"),
    (frozenset({"scuff"}), "脚轮地面留痕", "Caster scuff marks"),
    (frozenset({"caster"}), "脚轮质量差", "Poor caster quality"),
    (frozenset({"wheel"}), "脚轮质量差", "Poor caster quality"),
    (frozenset({"crushed"}), "运输包装破损", "Shipping package damage"),
    (frozenset({"box", "damaged"}), "运输包装破损", "Shipping package damage"),
    (frozenset({"packaging"}), "包装防护不足", "Insufficient packaging protection"),
    (frozenset({"carton"}), "外箱强度不足", "Weak shipping carton"),
    (frozenset({"instructions", "confusing"}), "说明书不清晰", "Unclear assembly instructions"),
    (frozenset({"manual"}), "说明书不清晰", "Unclear assembly instructions"),
    (frozenset({"assembly"}), "装配体验差", "Poor assembly experience"),
    (frozenset({"smell"}), "化学异味", "Chemical odor"),
    (frozenset({"odor"}), "化学异味", "Chemical odor"),
    (frozenset({"missing", "screws"}), "五金配件缺件", "Missing hardware"),
    (frozenset({"missing"}), "配件缺件", "Missing parts"),
    (frozenset({"screw"}), "五金配件问题", "Hardware issues"),
    (frozenset({"small"}), "尺寸偏小", "Smaller than expected"),
    (frozenset({"narrow"}), "尺寸偏窄", "Narrower than expected"),
    (frozenset({"sinks"}), "气压杆下坠", "Gas lift sinking"),
    (frozenset({"cylinder"}), "气压杆失效", "Gas lift failure"),
    (frozenset({"gas"}), "气压杆失效", "Gas lift failure"),
]


@dataclass
class FragmentInput:
    """聚类输入：一个评论片段及其向量。"""

    fragment_id: str
    review_id: str
    text: str
    rating: float | None
    language: str | None
    embedding: list[float]


@dataclass
class ClusterDraft:
    """聚类产出（api.md §5.1 痛点对象的无 ID 草稿形态）。"""

    name_zh: str
    name_en: str
    category: str
    frequency: int
    denominator: int
    severity: int
    severity_reason: str
    keywords: list[str] = field(default_factory=list)
    review_ids: list[str] = field(default_factory=list)
    fragment_ids: list[str] = field(default_factory=list)
    sample_text: str = ""
    sample_review_id: str = ""


def cosine_similarity(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def extract_keywords(texts: list[str], top: int = 6) -> list[str]:
    """簇内高频实词（去停用词），频次降序、字典序稳定。"""
    counts: dict[str, int] = {}
    for text in texts:
        for token in set(tokenize_for_embedding(text)):
            counts[token] = counts.get(token, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [token for token, _ in ordered[:top]]


def _variants(token: str) -> set[str]:
    """简单单复数归一：wheels→wheel，slides→slide 等。"""
    if token.endswith("s") and len(token) > 3:
        return {token, token[:-1]}
    return {token}


def _expand(tokens) -> set[str]:
    expanded: set[str] = set()
    for token in tokens:
        expanded |= _variants(token)
    return expanded


def _match_name(keywords: list[str], texts: list[str]) -> tuple[str, str]:
    """命名规则：最长模式优先，先按簇关键词匹配，再回退全文 token。

    全部命中关键词的规则优先级最高（主题词代表性最强），避免偶然
    出现在正文里的词抢先命名。
    """
    kw_set = _expand(keywords[:10])
    text_tokens = _expand(
        token for text in texts for token in tokenize_for_embedding(text)
    )
    rules = sorted(
        enumerate(_NAME_RULES), key=lambda pair: (-len(pair[1][0]), pair[0])
    )
    for use_keywords in (True, False):
        for _index, (pattern, zh, en) in rules:
            source = kw_set if use_keywords else text_tokens
            if all(word in source for word in pattern):
                return zh, en
    top = keywords[:2] or ["misc"]
    label = " / ".join(top)
    return f"{label} 相关投诉", f"Complaints about {label}"


def _match_category(keywords: list[str], texts: list[str]) -> str:
    joined = _expand(keywords)
    for text in texts:
        joined |= _expand(tokenize_for_embedding(text))
    for words, category in _CATEGORY_RULES:
        if joined & _expand(words):
            return category
    return "other"


def _severity(cluster_reviews: list[FragmentInput], frequency_ratio: float) -> tuple[int, str]:
    """确定性严重度 1–5：低星占比 + 频率占比 + 严重词（任务 §9 规则）。"""
    ratings = [f.rating for f in cluster_reviews if f.rating is not None]
    mean_rating = sum(ratings) / len(ratings) if ratings else 3.0
    low_star_ratio = (
        sum(1 for r in ratings if r <= 2) / len(ratings) if ratings else 0.0
    )
    tokens = _expand(
        token for f in cluster_reviews for token in tokenize_for_embedding(f.text)
    )
    raw_text = " ".join(f.text for f in cluster_reviews).lower()
    raw_tokens = set(_TOKEN_RE.findall(raw_text))
    has_severe = bool((tokens | raw_tokens) & SEVERE_WORDS)
    has_risk = bool((tokens | raw_tokens) & RISK_WORDS)

    score = 1
    reasons: list[str] = []
    if low_star_ratio >= 0.5 and mean_rating <= 2.0:
        score += 2
        reasons.append("簇内一半以上为 1–2 星评论")
    elif mean_rating <= 2.5:
        score += 1
        reasons.append("簇内平均星级偏低")
    if frequency_ratio >= 0.15:
        score += 1
        reasons.append(f"涉及评论占低星样本 {frequency_ratio:.0%}")
    if has_severe:
        score += 1
        reasons.append("出现断裂/失效类严重词")
    if has_risk:
        score += 1
        reasons.append("出现人身安全风险词")
    severity = max(1, min(5, score))
    if not reasons:
        reasons.append("低频且无严重词，属轻微抱怨")
    return severity, "；".join(reasons)


def cluster_fragments(
    fragments: list[FragmentInput], denominator: int
) -> tuple[list[ClusterDraft], int, int]:
    """阈值 leader 聚类。返回（top 簇草稿, 其他簇评论数, 未归类评论数）。

    frequency/評论数按独立评论去重；denominator 为聚类有效分母（1–3 星评论数）。
    """
    if not fragments:
        return [], 0, 0

    clusters: list[dict] = []  # {vectors, members, sample, sample_sim}
    for fragment in fragments:  # fragments 已按稳定顺序传入
        best: tuple[float, int] = (-1.0, -1)
        for index, cluster in enumerate(clusters):
            centroid = [
                sum(col) / len(cluster["vectors"]) for col in zip(*cluster["vectors"], strict=True)
            ]
            norm = math.sqrt(sum(value * value for value in centroid)) or 1.0
            similarity = cosine_similarity(fragment.embedding, centroid) / norm
            if similarity > best[0]:
                best = (similarity, index)
        if best[0] >= COSINE_THRESHOLD:
            target = clusters[best[1]]
            target["vectors"].append(fragment.embedding)
            target["members"].append(fragment)
            if best[0] > target["sample_sim"]:
                target["sample"] = fragment
                target["sample_sim"] = best[0]
        else:
            clusters.append(
                {
                    "vectors": [fragment.embedding],
                    "members": [fragment],
                    "sample": fragment,
                    "sample_sim": 1.0,
                }
            )

    drafts: list[ClusterDraft] = []
    other_review_count = 0
    singleton_reviews: set[str] = set()
    for cluster in clusters:
        members = cluster["members"]
        review_ids = list(dict.fromkeys(m.review_id for m in members))
        if len(review_ids) < MIN_CLUSTER_SIZE:
            singleton_reviews.update(review_ids)
            other_review_count += len(review_ids)
            continue
        texts = [m.text for m in members]
        keywords = extract_keywords(texts)
        name_zh, name_en = _match_name(keywords, texts)
        category = _match_category(keywords, texts)
        frequency = len(review_ids)
        ratio = frequency / denominator if denominator else 0.0
        severity, reason = _severity(members, ratio)
        sample = cluster["sample"]
        drafts.append(
            ClusterDraft(
                name_zh=name_zh,
                name_en=name_en,
                category=category,
                frequency=frequency,
                denominator=denominator,
                severity=severity,
                severity_reason=reason,
                keywords=keywords,
                review_ids=review_ids,
                fragment_ids=[m.fragment_id for m in members],
                sample_text=sample.text,
                sample_review_id=sample.review_id,
            )
        )

    # 确定性排序：频次降序、严重度降序、名称稳定序；取 Top 5。
    drafts.sort(key=lambda d: (-d.frequency, -d.severity, d.name_en, d.name_zh))
    top = drafts[:MAX_CLUSTERS]
    other_count = sum(d.frequency for d in drafts[MAX_CLUSTERS:])
    unclassified = len(singleton_reviews)
    return top, other_count, unclassified
